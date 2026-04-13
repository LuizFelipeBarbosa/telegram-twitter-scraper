import "@testing-library/jest-dom";

class ResizeObserverMock {
  observe() {}

  unobserve() {}

  disconnect() {}
}

Object.defineProperty(globalThis, "ResizeObserver", {
  writable: true,
  value: ResizeObserverMock,
});

const canvasContext2DMock = {
  save() {},
  restore() {},
  clearRect() {},
  scale() {},
  translate() {},
  beginPath() {},
  moveTo() {},
  lineTo() {},
  stroke() {},
  arc() {},
  fill() {},
  fillText() {},
  globalAlpha: 1,
  strokeStyle: "#000000",
  lineWidth: 1,
  fillStyle: "#000000",
  textAlign: "start",
  textBaseline: "alphabetic",
  font: "10px sans-serif",
} as unknown as CanvasRenderingContext2D;

Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
  writable: true,
  value(contextId: string) {
    if (contextId === "2d") {
      return canvasContext2DMock;
    }
    return null;
  },
});
