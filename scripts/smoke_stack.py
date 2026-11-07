"""Smoke test of the running local stack (docker compose), by hand, not in CI.

    uv run --project services/core-api python scripts/smoke_stack.py [--api URL] [--mail URL]

Steps (each prints PASS or FAIL; the first FAIL stops the run with exit code 1):
health -> sign up a throwaway account -> verify its email through Mailpit -> log in -> create a
subject -> upload a small PDF -> wait until indexed -> mark as textbook, outline -> hand in notes
-> cards made by the AI. Answering and grading is not covered: a card made today is asked from
the next learning day. The account is random and left in the database; its password is never
printed. Needs the stack from `docker compose --env-file .env -f infra/docker-compose.yml`.
"""

import argparse
import hashlib
import re
import secrets
import sys
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import httpx

POLL_SECONDS = 2.0


class Failed(Exception):
    pass


def make_pdf(pages: int = 3) -> bytes:
    """A small text PDF built by hand (Helvetica, no dependency)."""
    text = (
        "Chapter {n}. A network protocol is a set of rules for exchanging messages. "
        "The three-way handshake opens a TCP connection: SYN, SYN-ACK, ACK. "
        "TCP gives reliable ordered delivery; UDP gives fast delivery without guarantees."
    )
    objs: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(pages))}] "
        f"/Count {pages} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i in range(pages):
        lines = text.format(n=i + 1).split(". ")
        body = "BT /F1 12 Tf 50 740 Td 16 TL " + " ".join(f"({ln}.) Tj T*" for ln in lines) + " ET"
        stream = body.encode()
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {5 + 2 * i} 0 R "
            f"/Resources << /Font << /F1 3 0 R >> >> >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for n, obj in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def poll(
    what: str, probe: Callable[[], Any], *, timeout: float, interval: float = POLL_SECONDS
) -> Any:
    """Call `probe` until it returns something other than None, or fail after `timeout`."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = probe()
        if value is not None:
            return value
        time.sleep(interval)
    raise Failed(f"{what}: not ready after {timeout:.0f} s")


class Smoke:
    def __init__(self, api: str, mail: str) -> None:
        self.api = httpx.Client(base_url=api, timeout=60)
        self.mail = httpx.Client(base_url=mail, timeout=10)

    def step(self, name: str, fn: Callable[[], str | None]) -> None:
        started = time.monotonic()
        try:
            note = fn()
        except (Failed, httpx.HTTPError, KeyError, IndexError, AssertionError) as exc:
            print(f"FAIL {name} ({time.monotonic() - started:.1f}s): {type(exc).__name__} {exc}")
            raise SystemExit(1) from None
        print(f"PASS {name} ({time.monotonic() - started:.1f}s){' - ' + note if note else ''}")

    @staticmethod
    def ok(response: httpx.Response, *codes: int) -> Any:
        if response.status_code not in (codes or (200,)):
            # Only our own error codes are echoed; the request body (password) never is.
            raise Failed(
                f"{response.request.method} {response.request.url.path} -> "
                f"{response.status_code} {response.text[:200]}"
            )
        return response.json() if response.content else None


def run(api: str, mail: str) -> None:
    s = Smoke(api, mail)
    tag = secrets.token_hex(4)
    username = f"smoke{tag}"
    email = f"{username}@example.com"
    password = secrets.token_urlsafe(18)
    state: dict[str, Any] = {}

    def health() -> str | None:
        s.ok(s.api.get("/healthz"))
        return None

    def register() -> str | None:
        body = {"email": email, "password": password, "username": username}
        s.ok(s.api.post("/v1/auth/register", json=body), 202)
        return None

    def verify() -> str | None:
        def mail_token() -> str | None:
            found = s.mail.get("/api/v1/search", params={"query": f"to:{email}"}).json()
            for message in found.get("messages", []):
                body = s.mail.get(f"/api/v1/message/{message['ID']}").json()
                match = re.search(r"verify-email\?token=([A-Za-z0-9_\-]+)", body.get("Text", ""))
                if match:
                    return match.group(1)
            return None

        token = poll("verification email in Mailpit", mail_token, timeout=60)
        s.ok(s.api.post("/v1/auth/verify-email", json={"token": token}))
        return None

    def login() -> str | None:
        body = {"identifier": username, "password": password}
        data = s.ok(s.api.post("/v1/auth/login", json=body))
        assert data["email_verified"] is True
        s.api.headers["Authorization"] = f"Bearer {data['token']}"
        return None

    def subject() -> str | None:
        exam = (date.today() + timedelta(days=30)).isoformat()
        body = {"name": f"Smoke {tag}", "exam_date": exam}
        state["subject"] = s.ok(s.api.post("/v1/subjects", json=body), 201)["id"]
        return None

    def upload() -> str | None:
        pdf = make_pdf()
        body = {
            "filename": f"smoke-{tag}.pdf",
            "size_bytes": len(pdf),
            "sha256": hashlib.sha256(pdf).hexdigest(),
        }
        data = s.ok(s.api.post(f"/v1/subjects/{state['subject']}/documents", json=body), 200, 201)
        state["doc"] = data["document"]["id"]
        target = data["upload"]
        if target is not None:
            put = httpx.put(target["url"], content=pdf, headers=target["headers"], timeout=30)
            if put.status_code >= 300:
                raise Failed(f"PUT to storage -> {put.status_code}")
        s.ok(s.api.post(f"/v1/documents/{state['doc']}/confirm"), 200)
        return f"{len(pdf)} bytes"

    def indexed() -> str | None:
        def probe() -> str | None:
            doc = s.ok(s.api.get(f"/v1/documents/{state['doc']}"))
            if doc["status"] == "indexed":
                return doc["status"]
            if doc["status"] in ("failed", "rejected"):
                raise Failed(f"document status {doc['status']}: {doc.get('failure_reason')}")
            return None

        poll("document indexed", probe, timeout=240)
        return None

    def outline() -> str | None:
        s.ok(s.api.patch(f"/v1/documents/{state['doc']}", json={"role": "textbook"}))
        data = s.ok(s.api.get(f"/v1/subjects/{state['subject']}/outline"))
        sections = data["sections"]
        assert sections, f"no sections (reason={data.get('reason')})"
        state["section"] = sections[0]["id"]
        return f"{len(sections)} top-level sections"

    def submit_notes() -> str | None:
        draft = s.ok(s.api.post(f"/v1/subjects/{state['subject']}/submission-drafts"), 200, 201)
        state["session"] = draft["session_id"]
        body = {
            "session_id": state["session"],
            "description": "Studied the network protocol chapter",
            "text": (
                "The three-way handshake opens a TCP connection: SYN, SYN-ACK, ACK. "
                "TCP gives reliable ordered delivery; UDP is fast but gives no guarantees. "
                "A network protocol is a set of rules for exchanging messages."
            ),
        }
        s.ok(s.api.post("/v1/submissions", json=body), 200, 201)
        return None

    def cards() -> str | None:
        def probe() -> int | None:
            data = s.ok(s.api.get(f"/v1/vault/sessions/{state['session']}/result"))
            if data["submission_status"] == "failed":
                raise Failed("submission failed")
            if data["submission_status"] == "done":
                return data["cards"]
            return None

        count = poll("cards made from the notes (AI)", probe, timeout=240, interval=4)
        assert count > 0, "submission done but no cards"
        return f"{count} cards"

    s.step("health", health)
    s.step("register", register)
    s.step("verify email (Mailpit)", verify)
    s.step("login", login)
    s.step("create subject", subject)
    s.step("upload PDF", upload)
    s.step("document indexed", indexed)
    s.step("outline", outline)
    s.step("hand in notes", submit_notes)
    s.step("cards created", cards)
    # Not covered: answering and grading. A card made today is not asked until the next learning
    # day (`new_questions` skips cards saved today), so the review session is empty right now.
    print("SKIP answer and grade - new cards enter review the next learning day")
    print(f"ALL PASS (throwaway account {username})")


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--mail", default="http://localhost:8025")
    args = parser.parse_args()
    run(args.api, args.mail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
