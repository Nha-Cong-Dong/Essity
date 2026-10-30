"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { FilterChip } from "@/components/ui/filter-chip";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { graphFixture, SUBJECT_NAME, type GraphState } from "@/lib/fixtures/graph";
import { COPY, EDGE_KINDS, EDGE_STYLE, suggestList, viewGraph, type EdgeKind } from "@/lib/graph";

import { DetailPanel, type Selection } from "./detail-panel";
import { EdgeList } from "./edge-list";
import { Legend } from "./legend";

// T9.10a (US-19 AC1-AC6; DESIGN §6.15, .work/T9.10a/design-decisions.md): the graph screen from
// typed fixtures, no API. The canvas and the list read one filtered view and share one tray. The
// screen has no primary button except in the error state, no score and no nudge to tend the graph
// (AC6). Cytoscape loads here only, after the first paint.

const Canvas = dynamic(() => import("./graph-canvas"), {
  ssr: false,
  loading: () => <div aria-hidden="true" className="h-[50vh] min-h-70 rounded-sheet bg-sunken motion-safe:animate-pulse" />,
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
    <div aria-busy="true" aria-label="Đang tải đồ thị" className="mt-6 flex flex-col gap-4">
      <div aria-hidden="true" className="h-[50vh] min-h-70 rounded-sheet bg-sunken motion-safe:animate-pulse" />
    </div>
  );
}

function Notice({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div role="status" className="flex flex-col items-start gap-2 rounded-control border border-line bg-sheet p-3 text-caption">
      <p className="m-0">{children}</p>
      {action}
    </div>
  );
}

export function GraphScreen({ state }: { state: GraphState }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [retried, setRetried] = useState(false);
  const fixture = useMemo(() => graphFixture(retried ? "few" : state), [state, retried]);
  const reduced = useSyncExternalStore(subscribeReduced, reducedNow, () => false);

  const section = params.has("section") ? params.get("section")! : (fixture.sectionId ?? ALL);
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
        h.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "nearest" });
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
      <>
        <h1 className="m-0 text-title">Đồ thị</h1>
        <Skeleton />
      </>
    );
  }
  if (fixture.status === "error" || !data || !view || !everyKind) {
    return (
      <>
        <h1 className="m-0 text-title">Đồ thị</h1>
        <div role="alert" className="mt-8 flex flex-col items-start gap-4">
          <p className="m-0 text-read">{COPY.error}</p>
          <Button type="button" onClick={() => setRetried(true)}>
            Thử lại
          </Button>
        </div>
      </>
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
      <a href="#" className="inline-flex min-h-11 items-center text-meta underline">
        Về môn {SUBJECT_NAME}
      </a>
      <h1 className="m-0 text-title">Đồ thị</h1>

      <div className="mt-4 flex flex-col gap-3 min-[768px]:flex-row min-[768px]:items-end">
        <div className="flex min-w-0 flex-1 flex-col gap-1 min-[768px]:max-w-sm">
          <label htmlFor="graph-section" className="text-meta text-ink-soft">
            Mục
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

      <details className="mt-3 rounded-control border border-line px-3" data-kind-filter>
        <summary className="flex h-11 cursor-pointer items-center text-caption font-semibold">
          Loại liên kết{kindsOff ? ` (${kinds.size}/${EDGE_KINDS.length})` : ""}
        </summary>
        <div role="group" aria-label="Loại liên kết" className="flex flex-wrap gap-2 pb-3">
          {EDGE_KINDS.map((kind) => (
            <FilterChip
              key={kind}
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
      </details>

      <div className="mt-4 grid items-start gap-4 min-[1024px]:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-3" ref={frame}>
          {view.hidden > 0 && <Notice>{COPY.truncated}</Notice>}
          {noLinks ? (
            <div className="rounded-sheet bg-sheet p-6 shadow-sheet" data-empty>
              <p className="m-0 text-read">{COPY.empty}</p>
              <a href="#" className="mt-3 inline-flex min-h-11 items-center text-meta underline">
                Về môn
              </a>
            </div>
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
          onRemoveEdge={(id) => {
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
