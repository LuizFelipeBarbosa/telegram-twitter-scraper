import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { FilterBar } from "../components/FilterBar";
import { LandscapeMap } from "../components/LandscapeMap";
import { LandscapeTable } from "../components/LandscapeTable";
import { LoadingState } from "../components/LoadingState";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { fetchSnapshot } from "../lib/api";
import type { GraphNodeRow, NodeKind, PhaseKey, WindowKey } from "../lib/types";
import { Eyebrow, MetricCell, MetricsStrip, WindowSelector } from "../ui";

const ALL_PHASES: PhaseKey[] = ["emerging", "flash_event", "sustained", "fading", "steady"];
const DEFAULT_KINDS: NodeKind[] = ["event", "theme"];

export function LandscapeView() {
  const navigate = useNavigate();
  const [windowKey, setWindowKey] = useState<WindowKey>("7d");
  const [kindFilter, setKindFilter] = useState<Set<NodeKind>>(new Set(DEFAULT_KINDS));
  const [phaseFilter, setPhaseFilter] = useState<Set<string>>(new Set(ALL_PHASES));
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const snapshotState = useAsyncResource(
    () =>
      fetchSnapshot({
        window: windowKey,
        kinds: Array.from(kindFilter),
      }),
    [kindFilter, windowKey],
  );

  const allNodes: GraphNodeRow[] = snapshotState.data?.nodes ?? [];

  const filteredNodes = useMemo(() => {
    return allNodes.filter((node) => {
      if (!kindFilter.has(node.kind)) {
        return false;
      }
      if (node.kind !== "theme") {
        return true;
      }
      return node.phase == null || phaseFilter.has(String(node.phase));
    });
  }, [allNodes, kindFilter, phaseFilter]);

  const metrics = useMemo(() => {
    const total = allNodes.length;
    const themes = allNodes.filter((n) => n.kind === "theme").length;
    const events = allNodes.filter((n) => n.kind === "event").length;
    const emergingThemes = allNodes.filter(
      (n) => n.kind === "theme" && (n.phase === "emerging" || n.phase === "flash_event"),
    ).length;
    const relations = snapshotState.data?.relations.length ?? 0;
    return { total, themes, events, emergingThemes, relations };
  }, [allNodes, snapshotState.data?.relations.length]);

  const toggleKind = (kind: NodeKind) => {
    setKindFilter((previous) => {
      const next = new Set(previous);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
      }
      if (next.size === 0) {
        return new Set(DEFAULT_KINDS);
      }
      return next;
    });
  };

  const togglePhase = (phase: PhaseKey) => {
    setPhaseFilter((previous) => {
      const next = new Set(previous);
      if (next.has(phase)) {
        next.delete(phase);
      } else {
        next.add(phase);
      }
      if (next.size === 0) {
        return new Set(ALL_PHASES);
      }
      return next;
    });
  };

  if (snapshotState.loading) {
    return <LoadingState />;
  }

  if (snapshotState.error) {
    return <EmptyState title="Graph unavailable" message="The visualization API did not return a usable snapshot." />;
  }

  return (
    <section className="flex flex-col">
      <div className="flex items-end justify-between px-5 py-5 gap-4">
        <div>
          <Eyebrow>Live node landscape</Eyebrow>
          <h1 className="text-[clamp(1.8rem,4vw,2.4rem)] leading-[0.98] tracking-[-0.03em] mt-1">
            Event and theme pressure map
          </h1>
        </div>
        <WindowSelector value={windowKey} onChange={setWindowKey} />
      </div>

      <div className="mx-5">
        <MetricsStrip>
          <MetricCell label="Nodes" value={metrics.total} caption={`in ${windowKey} window`} />
          <MetricCell label="Themes" value={metrics.themes} caption="phase-tracked" />
          <MetricCell label="Events" value={metrics.events} caption="discrete moments" />
          <MetricCell label="Emerging" value={metrics.emergingThemes} caption="themes rising" />
          <MetricCell label="Relations" value={metrics.relations} caption="graph edges" />
        </MetricsStrip>
      </div>

      <FilterBar
        kinds={kindFilter}
        phases={phaseFilter}
        onKindToggle={toggleKind}
        onPhaseToggle={togglePhase}
      />

      {filteredNodes.length === 0 ? (
        <EmptyState
          title="No active nodes"
          message="This window and filter combination returned no nodes."
          suggestions={[
            { label: "Widen the window to 31d", onClick: () => setWindowKey("31d") },
            {
              label: "Enable all kinds",
              onClick: () =>
                setKindFilter(new Set(["event", "theme", "person", "nation", "org", "place"])),
            },
            { label: "Enable all phases", onClick: () => setPhaseFilter(new Set(ALL_PHASES)) },
          ]}
          onReset={() => {
            setKindFilter(new Set(DEFAULT_KINDS));
            setPhaseFilter(new Set(ALL_PHASES));
          }}
        />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] border-b border-ink">
          <div className="px-5 py-4 border-r border-ink/20">
            <LandscapeTable
              nodes={filteredNodes}
              hoveredNodeId={hoveredNodeId}
              onHover={setHoveredNodeId}
              onRowClick={(node) => navigate(`/node/${node.kind}/${node.slug}`)}
            />
          </div>
          <LandscapeMap
            nodes={filteredNodes}
            relations={snapshotState.data?.relations ?? []}
            hoveredNodeId={hoveredNodeId}
            onHover={setHoveredNodeId}
            onNodeClick={(node) => navigate(`/node/${node.kind}/${node.slug}`)}
          />
        </div>
      )}

      <div className="flex justify-between items-center px-5 py-3 font-mono text-[0.68rem] text-muted">
        <span>
          {allNodes.length} nodes · {filteredNodes.length} shown · sort by score desc
        </span>
        <span>window: {windowKey}</span>
      </div>
    </section>
  );
}
