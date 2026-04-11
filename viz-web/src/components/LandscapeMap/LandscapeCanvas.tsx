import { useEffect, useRef } from "react";
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";
import { KIND_STROKE } from "../../ui";
import type { PositionedNode } from "./useLandscapeLayout";
import type { DragState } from "./useLandscapeDrag";
import type { LandscapeZoomTransform } from "./useLandscapeZoom";

const PHASE_FILL: Record<string, string> = {
  emerging: "#C94F2B",
  flash_event: "#D97706",
  sustained: "#0D7C66",
  fading: "#2F6FB5",
  steady: "#5C4A39",
};

const NEUTRAL_FILL = "#F0E6D2";

interface LandscapeCanvasProps {
  nodes: PositionedNode[];
  relations: SnapshotRelation[];
  hoveredNodeId: string | null;
  dragState: DragState;
  transform: LandscapeZoomTransform;
  width: number;
  height: number;
}

function fillFor(node: GraphNodeRow): string {
  if (node.kind === "theme" && node.phase) {
    return PHASE_FILL[String(node.phase)] ?? NEUTRAL_FILL;
  }
  return NEUTRAL_FILL;
}

function isRelated(nodeId: string, hoveredId: string, relations: SnapshotRelation[]): boolean {
  return relations.some(
    (rel) =>
      (rel.source === hoveredId && rel.target === nodeId) ||
      (rel.target === hoveredId && rel.source === nodeId),
  );
}

function nodeOffset(node: PositionedNode, dragState: DragState): { x: number; y: number } {
  if (dragState.phase === "dragging" && dragState.nodeId === node.node_id) {
    return { x: node.x + dragState.dx, y: node.y + dragState.dy };
  }
  if (dragState.phase === "snapping-back" && dragState.nodeId === node.node_id) {
    const remaining = 1 - dragState.progress;
    return { x: node.x + remaining * dragState.fromDx, y: node.y + remaining * dragState.fromDy };
  }
  return { x: node.x, y: node.y };
}

export function LandscapeCanvas({
  nodes,
  relations,
  hoveredNodeId,
  dragState,
  transform,
  width,
  height,
}: LandscapeCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx.save();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.scale(dpr, dpr);
    ctx.translate(transform.x, transform.y);
    ctx.scale(transform.k, transform.k);

    // Relations (only when a node is hovered)
    if (hoveredNodeId) {
      ctx.strokeStyle = "#1A1715";
      for (const rel of relations) {
        if (rel.source !== hoveredNodeId && rel.target !== hoveredNodeId) continue;
        const src = nodes.find((n) => n.node_id === rel.source);
        const tgt = nodes.find((n) => n.node_id === rel.target);
        if (!src || !tgt) continue;
        const srcPos = nodeOffset(src, dragState);
        const tgtPos = nodeOffset(tgt, dragState);
        ctx.globalAlpha = Math.min(0.7, rel.score / 4);
        ctx.lineWidth = Math.max(1, rel.score);
        ctx.beginPath();
        ctx.moveTo(srcPos.x, srcPos.y);
        ctx.lineTo(tgtPos.x, tgtPos.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    // Bubbles
    for (const node of nodes) {
      const { x, y } = nodeOffset(node, dragState);
      const dimmed =
        hoveredNodeId !== null &&
        hoveredNodeId !== node.node_id &&
        !isRelated(node.node_id, hoveredNodeId, relations);

      ctx.globalAlpha = dimmed ? 0.16 : 0.9;
      ctx.fillStyle = fillFor(node);
      ctx.strokeStyle = KIND_STROKE[node.kind];
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(x, y, node.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Semantic label culling — only draw labels when effectively large enough on screen
      if (node.r * transform.k > 24) {
        ctx.globalAlpha = dimmed ? 0.18 : 1;
        ctx.fillStyle = "#1A1715";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.font = "600 13px Inter, system-ui, sans-serif";
        const label = node.display_name.length > 18 ? `${node.display_name.slice(0, 18)}…` : node.display_name;
        ctx.fillText(label, x, y - 4);
        ctx.font = "500 11px Inter, system-ui, sans-serif";
        ctx.globalAlpha = dimmed ? 0.14 : 0.75;
        ctx.fillText(node.kind, x, y + 10);
      }
    }

    ctx.restore();
  }, [nodes, relations, hoveredNodeId, dragState, transform, width, height]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 pointer-events-none"
      aria-hidden="true"
    />
  );
}
