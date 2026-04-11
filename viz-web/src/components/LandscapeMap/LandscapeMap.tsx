import { useCallback, useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent, type FocusEvent as ReactFocusEvent } from "react";
import type { GraphNodeRow, SnapshotRelation } from "../../lib/types";
import { useElementSize } from "../../hooks/useElementSize";
import { NodeTooltip } from "../NodeTooltip";
import { LandscapeCanvas } from "./LandscapeCanvas";
import { LandscapeControls } from "./LandscapeControls";
import { LandscapeHitLayer } from "./LandscapeHitLayer";
import { LandscapePreviewPopover } from "./LandscapePreviewPopover";
import { useLandscapeDrag } from "./useLandscapeDrag";
import { useLandscapeLayout, type PositionedNode } from "./useLandscapeLayout";
import { useLandscapeZoom, type LandscapeZoomTransform } from "./useLandscapeZoom";

const INITIAL_TRANSFORM: LandscapeZoomTransform = { x: 0, y: 0, k: 1 };
const CANVAS_HEIGHT = 520;

interface LandscapeMapProps {
  nodes: GraphNodeRow[];
  relations: SnapshotRelation[];
  hoveredNodeId: string | null;
  onHover: (nodeId: string | null) => void;
  onNodeClick: (node: GraphNodeRow) => void;
}

export function LandscapeMap({ nodes, relations, hoveredNodeId, onHover, onNodeClick }: LandscapeMapProps) {
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const zoomLayerRef = useRef<HTMLDivElement | null>(null);
  const { width } = useElementSize(container);
  const canvasWidth = Math.max(width, 720);

  const [transform, setTransform] = useState<LandscapeZoomTransform>(INITIAL_TRANSFORM);
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number; node: GraphNodeRow } | null>(null);
  const [previewNode, setPreviewNode] = useState<GraphNodeRow | null>(null);
  const [previewAnchor, setPreviewAnchor] = useState<{ x: number; y: number } | null>(null);

  const positioned = useLandscapeLayout(nodes, width);
  const drag = useLandscapeDrag();

  const handleTransformChange = useCallback((t: LandscapeZoomTransform) => {
    setTransform(t);
    if (zoomLayerRef.current) {
      zoomLayerRef.current.style.transform = `translate(${t.x}px, ${t.y}px) scale(${t.k})`;
    }
  }, []);

  const zoom = useLandscapeZoom({
    containerRef,
    onTransformChange: handleTransformChange,
  });

  const setContainerRef = useCallback((node: HTMLDivElement | null) => {
    setContainer(node);
    containerRef.current = node;
  }, []);

  const handleHover = useCallback(
    (nodeId: string | null, clientX: number, clientY: number) => {
      onHover(nodeId);
      if (nodeId) {
        const node = positioned.find((n) => n.node_id === nodeId);
        if (node) {
          setTooltipPos({ x: clientX + 10, y: clientY + 10, node });
        }
      }
    },
    [onHover, positioned],
  );

  const handleHoverEnd = useCallback(() => {
    onHover(null);
    setTooltipPos(null);
  }, [onHover]);

  const handleNodeClick = useCallback(
    (node: PositionedNode, event: ReactMouseEvent<HTMLButtonElement>) => {
      if (event.shiftKey) {
        setPreviewNode(node);
        setPreviewAnchor({ x: event.clientX, y: event.clientY });
      } else {
        onNodeClick(node);
      }
    },
    [onNodeClick],
  );

  const handlePointerDown = useCallback(
    (node: PositionedNode, event: ReactPointerEvent<HTMLButtonElement>) => {
      if (event.shiftKey || event.button !== 0) return;
      event.currentTarget.setPointerCapture?.(event.pointerId);
      drag.beginDrag(node.node_id, {
        clientX: event.clientX,
        clientY: event.clientY,
        button: event.button,
        shiftKey: event.shiftKey,
      });
    },
    [drag],
  );

  useEffect(() => {
    if (drag.state.phase !== "dragging") return;
    const handleMove = (event: PointerEvent) => {
      drag.updateDrag({ clientX: event.clientX, clientY: event.clientY });
    };
    const handleUp = () => {
      drag.endDrag();
    };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [drag]);

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      switch (event.key) {
        case "+":
        case "=":
          event.preventDefault();
          zoom.zoomIn();
          return;
        case "-":
        case "_":
          event.preventDefault();
          zoom.zoomOut();
          return;
        case "0":
          event.preventDefault();
          zoom.reset();
          return;
        case "ArrowLeft":
          event.preventDefault();
          zoom.panBy(48, 0);
          return;
        case "ArrowRight":
          event.preventDefault();
          zoom.panBy(-48, 0);
          return;
        case "ArrowUp":
          event.preventDefault();
          zoom.panBy(0, 48);
          return;
        case "ArrowDown":
          event.preventDefault();
          zoom.panBy(0, -48);
          return;
        case "Escape":
          setPreviewNode(null);
          setPreviewAnchor(null);
          return;
      }
    },
    [zoom],
  );

  const handleButtonKeyDown = useCallback(
    (node: PositionedNode, event: ReactKeyboardEvent<HTMLButtonElement>) => {
      if (event.key === "Enter" && event.shiftKey) {
        event.preventDefault();
        const rect = event.currentTarget.getBoundingClientRect();
        setPreviewNode(node);
        setPreviewAnchor({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
      }
    },
    [],
  );

  const handleFocus = useCallback(
    (node: PositionedNode, event: ReactFocusEvent<HTMLButtonElement>) => {
      const containerEl = containerRef.current;
      if (!containerEl) return;
      const buttonRect = event.currentTarget.getBoundingClientRect();
      const containerRect = containerEl.getBoundingClientRect();
      const outOfBounds =
        buttonRect.left < containerRect.left ||
        buttonRect.right > containerRect.right ||
        buttonRect.top < containerRect.top ||
        buttonRect.bottom > containerRect.bottom;
      if (outOfBounds) {
        zoom.panTo(node.x, node.y);
      }
    },
    [zoom],
  );

  return (
    <div className="p-4 bg-ink/[0.02]">
      <div className="flex items-baseline justify-between mb-2">
        <p className="uppercase tracking-[0.16em] text-[0.6rem] font-semibold text-muted">Heat map</p>
        <p className="font-mono text-[0.66rem] text-muted">ring = kind · fill = phase (themes) · size = score</p>
      </div>
      <div
        ref={setContainerRef}
        tabIndex={0}
        role="img"
        aria-label="Heat map of nodes"
        onKeyDown={handleKeyDown}
        className="relative border border-ink/15 bg-card rounded-sm overflow-hidden min-h-[420px] focus-visible:outline-2 focus-visible:outline-ink"
        style={{ height: CANVAS_HEIGHT }}
      >
        <LandscapeCanvas
          nodes={positioned}
          relations={relations}
          hoveredNodeId={hoveredNodeId}
          dragState={drag.state}
          transform={transform}
          width={canvasWidth}
          height={CANVAS_HEIGHT}
        />
        <div
          ref={zoomLayerRef}
          className="zoom-layer absolute inset-0 origin-top-left"
          style={{ transform: `translate(${transform.x}px, ${transform.y}px) scale(${transform.k})` }}
        >
          <LandscapeHitLayer
            nodes={positioned}
            dragState={drag.state}
            onHover={handleHover}
            onHoverEnd={handleHoverEnd}
            onNodeClick={handleNodeClick}
            onPointerDown={handlePointerDown}
            onKeyDown={handleButtonKeyDown}
            onFocus={handleFocus}
          />
        </div>
        <LandscapeControls
          scale={zoom.scale}
          onZoomIn={zoom.zoomIn}
          onZoomOut={zoom.zoomOut}
          onReset={zoom.reset}
        />
      </div>
      {tooltipPos ? <NodeTooltip x={tooltipPos.x} y={tooltipPos.y} node={tooltipPos.node} /> : null}
      {previewNode && previewAnchor ? (
        <LandscapePreviewPopover
          node={previewNode}
          x={previewAnchor.x}
          y={previewAnchor.y}
          onClose={() => {
            setPreviewNode(null);
            setPreviewAnchor(null);
          }}
          onNavigate={(node) => {
            setPreviewNode(null);
            setPreviewAnchor(null);
            onNodeClick(node);
          }}
        />
      ) : null}
    </div>
  );
}
