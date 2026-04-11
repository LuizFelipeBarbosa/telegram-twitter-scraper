import { useCallback, useEffect, useRef, useState } from "react";

export type DragState =
  | { phase: "idle" }
  | { phase: "dragging"; nodeId: string; dx: number; dy: number }
  | { phase: "snapping-back"; nodeId: string; fromDx: number; fromDy: number; progress: number };

interface BeginDragEvent {
  clientX: number;
  clientY: number;
  button: number;
  shiftKey: boolean;
}

interface UpdateDragEvent {
  clientX: number;
  clientY: number;
}

const SNAP_BACK_MS = 180;

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

export function useLandscapeDrag() {
  const [state, setState] = useState<DragState>({ phase: "idle" });
  const originRef = useRef<{ x: number; y: number } | null>(null);
  const snapTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const snapStartRef = useRef<number | null>(null);

  const beginDrag = useCallback((nodeId: string, event: BeginDragEvent) => {
    if (event.button !== 0 || event.shiftKey) {
      return;
    }
    originRef.current = { x: event.clientX, y: event.clientY };
    setState({ phase: "dragging", nodeId, dx: 0, dy: 0 });
  }, []);

  const updateDrag = useCallback((event: UpdateDragEvent) => {
    const origin = originRef.current;
    if (!origin) return;
    setState((prev) => {
      if (prev.phase !== "dragging") return prev;
      return {
        phase: "dragging",
        nodeId: prev.nodeId,
        dx: event.clientX - origin.x,
        dy: event.clientY - origin.y,
      };
    });
  }, []);

  const endDrag = useCallback(() => {
    setState((prev) => {
      if (prev.phase !== "dragging") return prev;
      snapStartRef.current = Date.now();
      const snap: DragState = {
        phase: "snapping-back",
        nodeId: prev.nodeId,
        fromDx: prev.dx,
        fromDy: prev.dy,
        progress: 0,
      };
      if (snapTimeoutRef.current) {
        clearTimeout(snapTimeoutRef.current);
      }
      snapTimeoutRef.current = setTimeout(() => {
        setState({ phase: "idle" });
        originRef.current = null;
        snapStartRef.current = null;
      }, SNAP_BACK_MS);
      return snap;
    });
  }, []);

  // rAF loop for snap-back progress updates during the 180ms window
  useEffect(() => {
    if (state.phase !== "snapping-back") return;
    let raf = 0;
    const tick = () => {
      const start = snapStartRef.current;
      if (!start) return;
      const elapsed = Date.now() - start;
      const progress = Math.min(1, elapsed / SNAP_BACK_MS);
      const eased = easeOutCubic(progress);
      setState((prev) => {
        if (prev.phase !== "snapping-back") return prev;
        return { ...prev, progress: eased };
      });
      if (progress < 1) {
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [state.phase]);

  useEffect(() => {
    return () => {
      if (snapTimeoutRef.current) {
        clearTimeout(snapTimeoutRef.current);
      }
    };
  }, []);

  return { state, beginDrag, updateDrag, endDrag };
}
