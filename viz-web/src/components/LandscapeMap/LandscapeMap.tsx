import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";
import { KIND_STROKE } from "../../ui";
import { useElementSize } from "../../hooks/useElementSize";
import { NodeTooltip } from "../NodeTooltip";
import { useLandscapeLayout, type PositionedNode } from "./useLandscapeLayout";

const PHASE_FILL: Record<string, string> = {
  emerging: "#C94F2B",
  flash_event: "#D97706",
  sustained: "#0D7C66",
  fading: "#2F6FB5",
  steady: "#5C4A39",
};

const NEUTRAL_FILL = "#F0E6D2";

interface LandscapeMapProps {
  nodes: GraphNodeRow[];
  relations: SnapshotRelation[];
  hoveredNodeId: string | null;
  onHover: (nodeId: string | null) => void;
  onNodeClick: (node: GraphNodeRow) => void;
}

interface NodeCircleProps {
  node: PositionedNode;
  fill: string;
  stroke: string;
  dimmed: boolean;
  onEnter: (node: PositionedNode, clientX: number, clientY: number) => void;
  onMove: (node: PositionedNode, clientX: number, clientY: number) => void;
  onLeave: () => void;
  onClick: (node: PositionedNode) => void;
}

function NodeCircle({ node, fill, stroke, dimmed, onEnter, onMove, onLeave, onClick }: NodeCircleProps) {
  const ref = useRef<SVGCircleElement | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) {
      return;
    }
    const handleEnter = (event: Event) => {
      const mouseEvent = event as MouseEvent;
      onEnter(node, mouseEvent.clientX, mouseEvent.clientY);
    };
    element.addEventListener("mouseenter", handleEnter);
    return () => {
      element.removeEventListener("mouseenter", handleEnter);
    };
  }, [node, onEnter]);

  return (
    <circle
      ref={ref}
      r={node.r}
      fill={fill}
      fillOpacity={dimmed ? 0.16 : 0.9}
      stroke={stroke}
      strokeWidth={3}
      filter="url(#bubbleGlow)"
      style={{ cursor: "pointer" }}
      onMouseMove={(event) => onMove(node, event.clientX, event.clientY)}
      onMouseLeave={onLeave}
      onClick={() => onClick(node)}
    />
  );
}

export function LandscapeMap({ nodes, relations, hoveredNodeId, onHover, onNodeClick }: LandscapeMapProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const { width } = useElementSize(container);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number; node: GraphNodeRow } | null>(null);

  const positioned = useLandscapeLayout(nodes, width);

  const visibleRelations = useMemo(() => {
    if (!hoveredNodeId) {
      return [] as SnapshotRelation[];
    }
    return relations.filter((rel) => rel.source === hoveredNodeId || rel.target === hoveredNodeId);
  }, [hoveredNodeId, relations]);

  const fillFor = (node: GraphNodeRow): string => {
    if (node.kind === "theme" && node.phase) {
      return PHASE_FILL[String(node.phase)] ?? NEUTRAL_FILL;
    }
    return NEUTRAL_FILL;
  };

  const handleEnter = (node: PositionedNode, clientX: number, clientY: number) => {
    onHover(node.node_id);
    setTooltipPos({ x: clientX + 10, y: clientY + 10, node });
  };

  const handleMove = (node: PositionedNode, clientX: number, clientY: number) => {
    setTooltipPos({ x: clientX + 10, y: clientY + 10, node });
  };

  const handleLeave = () => {
    onHover(null);
    setTooltipPos(null);
  };

  return (
    <div className="p-4 bg-ink/[0.02]">
      <div className="flex items-baseline justify-between mb-2">
        <p className="uppercase tracking-[0.16em] text-[0.6rem] font-semibold text-muted">Heat map</p>
        <p className="font-mono text-[0.66rem] text-muted">ring = kind · fill = phase (themes) · size = score</p>
      </div>
      <div ref={setContainer} className="relative border border-ink/15 bg-card rounded-sm overflow-hidden">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${Math.max(width, 720)} 520`}
          className="w-full h-auto min-h-[420px]"
          role="img"
          aria-label="Heat map of nodes"
        >
          <defs>
            <filter id="bubbleGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="14" stdDeviation="16" floodOpacity="0.14" />
            </filter>
          </defs>

          {visibleRelations.map((rel) => {
            const source = positioned.find((p) => p.node_id === rel.source);
            const target = positioned.find((p) => p.node_id === rel.target);
            if (!source || !target) {
              return null;
            }
            return (
              <line
                key={`${rel.source}-${rel.target}`}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#1A1715"
                strokeOpacity={Math.min(0.7, rel.score / 4)}
                strokeWidth={Math.max(1, rel.score)}
              />
            );
          })}

          {positioned.map((node) => {
            const dimmed =
              hoveredNodeId !== null &&
              hoveredNodeId !== node.node_id &&
              !visibleRelations.some((r) => r.source === node.node_id || r.target === node.node_id);
            return (
              <g key={node.node_id} transform={`translate(${node.x}, ${node.y})`}>
                <NodeCircle
                  node={node}
                  fill={fillFor(node)}
                  stroke={KIND_STROKE[node.kind]}
                  dimmed={dimmed}
                  onEnter={handleEnter}
                  onMove={handleMove}
                  onLeave={handleLeave}
                  onClick={onNodeClick}
                />
                {node.r > 24 ? (
                  <text
                    textAnchor="middle"
                    className="fill-ink"
                    style={{ pointerEvents: "none", opacity: dimmed ? 0.18 : 1, fontSize: "0.82rem", fontWeight: 600 }}
                  >
                    <tspan x="0" dy="-0.1em">
                      {node.display_name.length > 18 ? `${node.display_name.slice(0, 18)}…` : node.display_name}
                    </tspan>
                    <tspan x="0" dy="1.3em" style={{ fontSize: "0.68rem", fontWeight: 500, opacity: 0.75 }}>
                      {node.kind}
                    </tspan>
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>
      {tooltipPos ? <NodeTooltip x={tooltipPos.x} y={tooltipPos.y} node={tooltipPos.node} /> : null}
    </div>
  );
}
