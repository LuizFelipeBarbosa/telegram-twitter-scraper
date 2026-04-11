import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LandscapeControls } from "./LandscapeControls";

describe("LandscapeControls", () => {
  it("renders zoom in, zoom out, and reset buttons", () => {
    render(
      <LandscapeControls scale={1} onZoomIn={() => undefined} onZoomOut={() => undefined} onReset={() => undefined} />,
    );
    expect(screen.getByRole("button", { name: /zoom in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /zoom out/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset/i })).toBeInTheDocument();
  });

  it("renders scale indicator with formatted value", () => {
    render(
      <LandscapeControls scale={1.42} onZoomIn={() => undefined} onZoomOut={() => undefined} onReset={() => undefined} />,
    );
    expect(screen.getByText(/×\s*1\.42/)).toBeInTheDocument();
  });

  it("clicking zoom in button calls onZoomIn", async () => {
    const handler = vi.fn();
    render(
      <LandscapeControls scale={1} onZoomIn={handler} onZoomOut={() => undefined} onReset={() => undefined} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /zoom in/i }));
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("clicking reset button calls onReset", async () => {
    const handler = vi.fn();
    render(
      <LandscapeControls scale={2} onZoomIn={() => undefined} onZoomOut={() => undefined} onReset={handler} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /reset/i }));
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
