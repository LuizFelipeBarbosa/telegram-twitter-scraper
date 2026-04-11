import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useLandscapeDrag } from "./useLandscapeDrag";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useLandscapeDrag", () => {
  it("initial state is idle", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    expect(result.current.state.phase).toBe("idle");
  });

  it("beginDrag with button 0 transitions to dragging", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    act(() => {
      result.current.beginDrag("node-1", { clientX: 100, clientY: 200, button: 0, shiftKey: false });
    });
    expect(result.current.state.phase).toBe("dragging");
    if (result.current.state.phase === "dragging") {
      expect(result.current.state.nodeId).toBe("node-1");
      expect(result.current.state.dx).toBe(0);
      expect(result.current.state.dy).toBe(0);
    }
  });

  it("updateDrag updates dx/dy", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    act(() => {
      result.current.beginDrag("node-1", { clientX: 100, clientY: 200, button: 0, shiftKey: false });
      result.current.updateDrag({ clientX: 130, clientY: 240 });
    });
    expect(result.current.state.phase).toBe("dragging");
    if (result.current.state.phase === "dragging") {
      expect(result.current.state.dx).toBe(30);
      expect(result.current.state.dy).toBe(40);
    }
  });

  it("endDrag transitions to snapping-back then back to idle after 180ms", () => {
    const { result } = renderHook(() => useLandscapeDrag());
    act(() => {
      result.current.beginDrag("node-1", { clientX: 100, clientY: 200, button: 0, shiftKey: false });
      result.current.updateDrag({ clientX: 150, clientY: 260 });
      result.current.endDrag();
    });
    expect(result.current.state.phase).toBe("snapping-back");
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(result.current.state.phase).toBe("idle");
  });
});
