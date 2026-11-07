"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { Doodle } from "@/components/icons/doodle";
import { BackLink, Block } from "@/components/screen-kit";
import { Button } from "@/components/ui/button";
import { FilterChip } from "@/components/ui/filter-chip";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { graphFixture, SUBJECT_NAME, type GraphFixture, type GraphState } from "@/lib/fixtures/graph";
import { COPY, EDGE_KINDS, EDGE_STYLE, suggestList, viewGraph, type EdgeKind, type GraphData } from "@/lib/graph";

import { DetailPanel, type Selection } from "./detail-panel";
import { EdgeList } from "./edge-list";
import { Legend } from "./legend";

// T9.10a (US-19 AC1-AC6; DESIGN §6.15, .work/T9.10a/design-decisions.md): the graph screen from
// typed fixtures, no API. The canvas and the list read one filtered view and share one tray. The
// screen has no primary button except in the error state, no score and no nudge to tend the graph
// (AC6). Cytoscape loads here only, after the first paint.

const Canvas = dynamic(() => import("./graph-canvas"), {
  ssr: false,
  loading: () => <div aria-hidden="true" className="h-[50vh] min-h-70 rounded-tile bg-sunken motion-safe:animate-pulse" />,
});

const ALL = "";
const REDUCED = "(prefers-reduced-motion: reduce)";
const subscribeReduced = (cb: () => void) => {
  const mq = typeof window.matchMedia === "function" ? window.matchMedia(REDUCED) : null;
  mq?.addEventListener("change", cb);
  return () => mq?.removeEventListener("change", cb);
};
const reducedNow = () => (typeof window.matchMedia === "function" ? window.matchMedia(REDUCED).matches : false);

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Đang tải đồ thị" className="flex flex-col gap-4">
      <div aria-hidden="true" className="h-[50vh] min-h-70 rounded-tile bg-sunken motion-safe:animate-pulse" />
    </div>
  );
}

function Notice({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div role="status" className="flex flex-col items-start gap-2 rounded-tile border border-line bg-sheet p-4 text-meta">
      <p className="m-0">{children}</p>
      {action}
    </div>
  );
}

/** T9.10: the screen on real data. The section filter is the URL's `section`, read again by the page. */
export type LiveGraph = { subjectId: string; subjectName: string; data: GraphData };

export function GraphScreen({ state = "few", live }: { state?: GraphState; live?: LiveGraph }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [retried, setRetried] = useState(false);
  const fixture = useMemo<GraphFixture>(
    () =>
      live
        ? { data: live.data, sectionId: null, kinds: [...EDGE_KINDS], selectedId: null, view: "graph", status: "ready" }
        : graphFixture(retried ? "few" : state),
    [state, retried, live],
  );
  const subjectName = live ? live.subjectName : SUBJECT_NAME;
  const subjectHref = live ? `/subjects/${live.subjectId}` : "#";
  const reduced = useSyncExternalStore(subscribeReduced, reducedNow, () => false);

  const wanted = params.has("section") ? params.get("section")! : (fixture.sectionId ?? ALL);
  // A section that is not in the data (a stale link) shows the whole subject.
  const section = live && !live.data.sections.some((s) => s.id === wanted) ? ALL : wanted;
  const kinds = useMemo(() => {
    const raw = params.get("edge");
    if (raw === null) return new Set<EdgeKind>(fixture.kinds);
    return new Set(raw.split(",").filter((k): k is EdgeKind => (EDGE_KINDS as readonly string[]).includes(k)));
  }, [params, fixture]);
  const listView = (params.get("view") ?? fixture.view) === "list";

  const [selection, setSelection] = useState<Selection | null>(
    fixture.selectedId ? { kind: "card", id: fixture.selectedId } : null,
  );
  const [removed, setRemoved] = useState<ReadonlySet<string>>(new Set());
  const [unlinked, setUnlinked] = useState<"done" | "failed" | null>(null);

  const data = useMemo(
    () => (fixture.data ? { ...fixture.data, edges: fixture.data.edges.filter((e) => !removed.has(e.id)) } : null),
    [fixture, removed],
  );
  const view = useMemo(() => (data ? viewGraph(data, section === ALL ? null : section, kinds) : null), [data, section, kinds]);
  const everyKind = useMemo(
    () => (data ? viewGraph(data, section === ALL ? null : section, new Set(EDGE_KINDS)) : null),
    [data, section],
  );

  const [frameWidth, setFrameWidth] = useState(1024);
  const frame = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = frame.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setFrameWidth(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [state, retried]);

  // Moving into the tray: a keyboard user lands on its heading; a pointer user is only scrolled
  // there if the tray is out of sight (no jump when it is already visible).
  const lastKey = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const firstPick = useRef(true);
  const picked = selection ? `${selection.kind}:${selection.id}` : null;
  useEffect(() => {
    if (firstPick.current) {
      firstPick.current = false;
      return;
    }
    const h = heading.current;
    if (picked === null || !h) return;
    if (lastKey.current) {
      h.focus();
    } else {
      const r = h.getBoundingClientRect();
      if (r.top < 0 || r.bottom > window.innerHeight) {
        // Under 1024 px the tray sits below the canvas: bring it to the top so "Chi tiết" shows.
        const below = window.innerWidth < 1024;
        h.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: below ? "start" : "nearest" });
      }
    }
  }, [picked, reduced]);

  const switchRef = useRef<HTMLButtonElement>(null);

  function put(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }
  const setKinds = (next: Set<EdgeKind>) => put({ edge: [...next].join(",") });

  if (fixture.status === "loading") {
    return (
      <div className="flex flex-col gap-4">
        <BackLink href={subjectHref}>Về môn {subjectName}</BackLink>
        <h1 className="m-0 text-title">Đồ thị</h1>
        <Skeleton />
      </div>
    );
  }
  if (fixture.status === "error" || !data || !view || !everyKind) {
    return (
      <div className="flex flex-col gap-4">
        <BackLink href={subjectHref}>Về môn {subjectName}</BackLink>
        <h1 className="m-0 text-title">Đồ thị</h1>
        <Block tier="sheet" role="alert" className="flex flex-col items-start gap-4">
          <p className="m-0 text-read">{COPY.error}</p>
          <Button type="button" onClick={() => setRetried(true)}>
            Thử lại
          </Button>
        </Block>
      </div>
    );
  }

  const noLinks = everyKind.edges.length === 0;
  const kindsOff = kinds.size < EDGE_KINDS.length;
  const noneOfKind = !noLinks && view.edges.length === 0;

  return (
    <div
      data-graph-screen
      onKeyDownCapture={() => (lastKey.current = true)}
      onPointerDownCapture={() => (lastKey.current = false)}
    >
      <BackLink href={subjectHref}>Về môn {subjectName}</BackLink>
      <h1 className="m-0 mt-1 text-title">Đồ thị</h1>

      <Block as="section" tier="sheet" aria-label="Bộ lọc đồ thị" className="mt-2 flex flex-col gap-2 p-3 min-[641px]:mt-4 min-[641px]:gap-3 min-[641px]:p-4 min-[901px]:p-5">
      <div className="flex flex-col gap-3 min-[768px]:flex-row min-[768px]:items-end">
        <div className="flex min-w-0 flex-1 flex-col gap-1 min-[768px]:max-w-sm">
          <label htmlFor="graph-section" className="text-meta text-ink-soft">
            Phần
          </label>
          <Select
            id="graph-section"
            value={section}
            onChange={(e) => {
              setSelection(null);
              put({ section: e.target.value });
            }}
          >
            <option value={ALL}>Cả môn</option>
            {data.sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.parentId ? "— " : ""}
                {s.title}
              </option>
            ))}
          </Select>
        </div>
        <Switch
          ref={switchRef}
          checked={listView}
          onCheckedChange={(on) => put({ view: on ? "list" : "graph" })}
        >
          Xem dạng danh sách
        </Switch>
      </div>

      <div role="group" aria-label="Loại liên kết" data-kind-filter className="flex flex-wrap items-center gap-2">
        <span className="text-meta text-ink-soft">
          Loại liên kết{kindsOff ? ` (${kinds.size}/${EDGE_KINDS.length})` : ""}
        </span>
        {EDGE_KINDS.map((kind) => (
          <FilterChip
            key={kind}
            className="rounded-full"
            checked={kinds.has(kind)}
            onCheckedChange={(on) => {
              const next = new Set(kinds);
              if (on) next.add(kind);
              else next.delete(kind);
              setKinds(next);
            }}
          >
            {EDGE_STYLE[kind].label}
          </FilterChip>
        ))}
      </div>
      </Block>

      <div className="mt-4 grid items-start gap-4 min-[1024px]:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-3" ref={frame}>
          {view.hidden > 0 && <Notice>{COPY.truncated}</Notice>}
          {noLinks ? (
            <Block tier="tint" data-empty>
              <Doodle name="do-thi" size={48} className="mb-2 text-hong-text" />
              <p className="m-0 text-read">{COPY.empty}</p>
              {view.cards.length === 0 && live && (
                <a
                  href={`/subjects/${live.subjectId}/sessions/new`}
                  className="mt-3 mr-4 inline-flex min-h-11 items-center font-semibold rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken"
                >
                  Ghi buổi học
                </a>
              )}
              <BackLink href={subjectHref} className="mt-3">
                Về môn
              </BackLink>
            </Block>
          ) : (
            <>
              {noneOfKind && (
                <Notice
                  action={
                    <Button type="button" variant="quiet" onClick={() => setKinds(new Set(EDGE_KINDS))}>
                      Bật lại tất cả
                    </Button>
                  }
                >
                  {COPY.noKind}
                </Notice>
              )}
              {!listView && suggestList(view.cards.length, frameWidth) && (
                <Notice
                  action={
                    <Button type="button" variant="quiet" onClick={() => put({ view: "list" })}>
                      Xem dạng danh sách
                    </Button>
                  }
                >
                  <span>Nhiều thẻ, chọn qua danh sách sẽ dễ hơn.</span>
                </Notice>
              )}
              {listView ? (
                <EdgeList
                  view={view}
                  selectedId={selection?.kind === "card" ? selection.id : null}
                  onSelectCard={(id) => setSelection({ kind: "card", id })}
                />
              ) : (
                <>
                  <Canvas
                    view={view}
                    sections={data.sections}
                    selectedId={selection?.kind === "card" ? selection.id : null}
                    reducedMotion={reduced}
                    onSelectCard={(id) => {
                      setUnlinked(null);
                      setSelection({ kind: "card", id });
                    }}
                    onSelectEdge={(id) => {
                      setUnlinked(null);
                      setSelection({ kind: "edge", id });
                    }}
                  />
                  <p className="m-0 text-caption text-ink-soft" data-graph-summary>
                    Đồ thị có {view.cards.length} thẻ và {view.edges.length} liên kết. Duyệt bằng bàn phím ở dạng danh sách.
                  </p>
                </>
              )}
            </>
          )}
          <Legend />
        </div>

        <DetailPanel
          view={view}
          selection={selection}
          headingRef={heading}
          unlink={unlinked}
          onSelectCard={(id) => {
            setUnlinked(null);
            setSelection({ kind: "card", id });
          }}
          onBackToGraph={() => {
            frame.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
            switchRef.current?.focus();
          }}
          onClose={() => setSelection(null)}
          vaultHref={live ? `/kho-kien-thuc?subject=${live.subjectId}` : undefined}
          onRemoveEdge={live ? undefined : (id) => {
            // Static preview: the unlink works on the fixture only; T9.10 calls the T9.2 command.
            setRemoved((prev) => new Set(prev).add(id));
            setSelection(null);
            setUnlinked("done");
          }}
        />
      </div>
      <p role="status" className="sr-only">
        {unlinked === "done" ? "Đã gỡ liên kết." : ""}
      </p>
    </div>
  );
}
