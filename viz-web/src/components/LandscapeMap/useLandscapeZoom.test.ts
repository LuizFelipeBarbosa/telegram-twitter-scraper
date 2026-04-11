import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useLandscapeZoom } from "./useLandscapeZoom";
import { useRef } from "react";

function setup() {
  const container = document.createElement("div");
  Object.defineProperty(container, "clientWidth", { value: 800, configurable: true });
  Object.defineProperty(container, "clientHeight", { value: 600, configurable: true });
  document.body.appendChild(container);
  const onTransformChange = vi.fn();
  const hookResult = renderHook(() => {
    const ref = useRef<HTMLDivElement | null>(container);
    return useLandscapeZoom({ containerRef: ref, onTransformChange });
  });
  return { container, onTransformChange, ...hookResult };
}

describe("useLandscapeZoom", () => {
  it("starts at scale 1", () => {
    const { result } = setup();
    expect(result.current.scale).toBe(1);
  });

  it("zoomIn multiplies scale by 1.4", () => {
    const { result } = setup();
    act(() => {
      result.current.zoomIn();
    });
    expect(result.current.scale).toBeCloseTo(1.4, 5);
  });

  it("zoomOut divides scale by 1.4", () => {
    const { result } = setup();
    act(() => {
      result.current.zoomIn();
      result.current.zoomOut();
    });
    expect(result.current.scale).toBeCloseTo(1, 5);
  });

  it("reset returns scale to 1", () => {
    const { result } = setup();
    act(() => {
      result.current.zoomIn();
      result.current.zoomIn();
      result.current.reset();
    });
    expect(result.current.scale).toBe(1);
  });
});
