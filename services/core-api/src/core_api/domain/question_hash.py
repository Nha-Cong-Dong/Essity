"""The content hash of a question (plan D3): the same question, however it was typed, has the
same hash, so a seed run twice adds nothing (T2.2).

Normalised: Unicode NFC, whitespace trimmed and runs of whitespace made one space. Case is kept:
"N" and "n" are different symbols in a formula. A version prefix lets the normalisation change
later without colliding with old hashes.
"""

import hashlib
import unicodedata

VERSION = "v1"


def content_hash(prompt: str) -> str:
    normalised = " ".join(unicodedata.normalize("NFC", prompt).split())
    return hashlib.sha256(f"{VERSION}\n{normalised}".encode()).hexdigest()
