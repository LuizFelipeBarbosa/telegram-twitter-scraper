import * as d3 from "d3";
import { useMemo } from "react";
import type { GraphNodeRow } from "../../lib/types";

export type PositionedNode = GraphNodeRow & { x: number; y: number; r: number };

export function useLandscapeLayout(nodes: GraphNodeRow[], width: number): PositionedNode[] {
  return useMemo<PositionedNode[]>(() => {
    if (nodes.length === 0) {
      return [];
    }
    const canvasWidth = Math.max(width, 720);
    const radius = d3
      .scaleSqrt<number, number>()
      .domain([0, d3.max(nodes, (n) => n.score) ?? 1])
      .range([16, 78]);

    const initial: PositionedNode[] = nodes.map((node, index) => ({
      ...node,
      x: canvasWidth / 2 + ((index % 6) - 3) * 20,
      y: 260 + (Math.floor(index / 6) - 3) * 20,
      r: radius(node.score),
    }));

    const simulation = d3
      .forceSimulation(initial)
      .force("x", d3.forceX<PositionedNode>(canvasWidth / 2).strength(0.06))
      .force("y", d3.forceY<PositionedNode>(260).strength(0.08))
      .force("charge", d3.forceManyBody<PositionedNode>().strength(-22))
      .force("collision", d3.forceCollide<PositionedNode>((n) => n.r + 6))
      .stop();

    for (let i = 0; i < 180; i += 1) {
      simulation.tick();
    }
    return initial;
  }, [nodes, width]);
}
