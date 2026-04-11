import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent, KeyboardEvent as ReactKeyboardEvent, FocusEvent as ReactFocusEvent } from "react";
import type { PositionedNode } from "./useLandscapeLayout";
import type { DragState } from "./useLandscapeDrag";

interface LandscapeHitLayerProps {
  nodes: PositionedNode[];
  dragState: DragState;
  onHover: (nodeId: string | null, clientX: number, clientY: number) => void;
  onHoverEnd: () => void;
  onNodeClick: (node: PositionedNode, event: ReactMouseEvent<HTMLButtonElement>) => void;
  onPointerDown: (node: PositionedNode, event: ReactPointerEvent<HTMLButtonElement>) => void;
  onKeyDown: (node: PositionedNode, event: ReactKeyboardEvent<HTMLButtonElement>) => void;
  onFocus: (node: PositionedNode, event: ReactFocusEvent<HTMLButtonElement>) => void;
}

function ariaLabelFor(node: PositionedNode): string {
  const kindLabel = node.kind;
  return `${node.display_name}, ${kindLabel}, score ${node.score.toFixed(2)}`;
}

export function LandscapeHitLayer({
  nodes,
  dragState,
  onHover,
  onHoverEnd,
  onNodeClick,
  onPointerDown,
  onKeyDown,
  onFocus,
}: LandscapeHitLayerProps) {
  return (
    <div className="hit-layer absolute inset-0" data-testid="landscape-hit-layer">
      {nodes.map((node) => {
        const isDragging = dragState.phase === "dragging" && dragState.nodeId === node.node_id;
        const dragOffsetX = isDragging ? dragState.dx : 0;
        const dragOffsetY = isDragging ? dragState.dy : 0;
        return (
          <button
            key={node.node_id}
            type="button"
            data-node-id={node.node_id}
            aria-label={ariaLabelFor(node)}
            tabIndex={0}
            onMouseEnter={(event) => onHover(node.node_id, event.clientX, event.clientY)}
            onMouseMove={(event) => onHover(node.node_id, event.clientX, event.clientY)}
            onMouseLeave={onHoverEnd}
            onFocus={(event) => onFocus(node, event)}
            onClick={(event) => onNodeClick(node, event)}
            onPointerDown={(event) => onPointerDown(node, event)}
            onKeyDown={(event) => onKeyDown(node, event)}
            className="absolute rounded-full bg-transparent border-0 p-0 cursor-pointer focus-visible:outline-2 focus-visible:outline-phase-emerging focus-visible:outline-offset-2"
            style={{
              left: `${node.x - node.r + dragOffsetX}px`,
              top: `${node.y - node.r + dragOffsetY}px`,
              width: `${node.r * 2}px`,
              height: `${node.r * 2}px`,
            }}
          />
        );
      })}
    </div>
  );
}
