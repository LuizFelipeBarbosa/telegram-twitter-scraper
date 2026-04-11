import * as d3 from "d3";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

export interface LandscapeZoomTransform {
  x: number;
  y: number;
  k: number;
}

interface UseLandscapeZoomOptions {
  containerRef: RefObject<HTMLDivElement | null>;
  onTransformChange?: (transform: LandscapeZoomTransform) => void;
}

const ZOOM_STEP = 1.4;
const SCALE_MIN = 0.5;
const SCALE_MAX = 8;

export function useLandscapeZoom({ containerRef, onTransformChange }: UseLandscapeZoomOptions) {
  const [scale, setScale] = useState(1);
  const zoomBehaviorRef = useRef<d3.ZoomBehavior<HTMLDivElement, unknown> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) {
      return;
    }
    const selection = d3.select(el as HTMLDivElement);
    const behavior = d3
      .zoom<HTMLDivElement, unknown>()
      .scaleExtent([SCALE_MIN, SCALE_MAX])
      .filter((event: Event) => {
        const target = event.target as Element | null;
        if (target && target.closest("[data-node-id]")) {
          return false;
        }
        if (event.type === "wheel") return true;
        if (event.type === "pointerdown" && (event as PointerEvent).button === 0) return true;
        if (event.type === "mousedown" && (event as MouseEvent).button === 0) return true;
        return false;
      })
      .on("zoom", (event) => {
        const { x, y, k } = event.transform;
        setScale(k);
        onTransformChange?.({ x, y, k });
      });
    selection.call(behavior);
    zoomBehaviorRef.current = behavior;
    return () => {
      selection.on(".zoom", null);
      zoomBehaviorRef.current = null;
    };
  }, [containerRef, onTransformChange]);

  const zoomIn = useCallback(() => {
    setScale((s) => Math.min(SCALE_MAX, s * ZOOM_STEP));
    const el = containerRef.current;
    const behavior = zoomBehaviorRef.current;
    if (el && behavior) {
      d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.scaleBy, ZOOM_STEP);
    }
  }, [containerRef]);

  const zoomOut = useCallback(() => {
    setScale((s) => Math.max(SCALE_MIN, s / ZOOM_STEP));
    const el = containerRef.current;
    const behavior = zoomBehaviorRef.current;
    if (el && behavior) {
      d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.scaleBy, 1 / ZOOM_STEP);
    }
  }, [containerRef]);

  const reset = useCallback(() => {
    setScale(1);
    const el = containerRef.current;
    const behavior = zoomBehaviorRef.current;
    if (el && behavior) {
      d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.transform, d3.zoomIdentity);
    }
  }, [containerRef]);

  const panBy = useCallback(
    (dx: number, dy: number) => {
      const el = containerRef.current;
      const behavior = zoomBehaviorRef.current;
      if (!el || !behavior) return;
      d3.select(el as HTMLDivElement).transition().duration(180).call(behavior.translateBy, dx, dy);
    },
    [containerRef],
  );

  const panTo = useCallback(
    (x: number, y: number) => {
      const el = containerRef.current;
      const behavior = zoomBehaviorRef.current;
      if (!el || !behavior) return;
      const rect = el.getBoundingClientRect();
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      d3.select(el as HTMLDivElement)
        .transition()
        .duration(180)
        .call(behavior.translateTo, x, y, [centerX, centerY]);
    },
    [containerRef],
  );

  return { scale, zoomIn, zoomOut, reset, panBy, panTo };
}
