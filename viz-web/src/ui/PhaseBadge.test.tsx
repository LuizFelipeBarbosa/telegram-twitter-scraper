import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PhaseBadge } from "./PhaseBadge";

describe("PhaseBadge", () => {
  it("renders emerging label and emerging tint", () => {
    render(<PhaseBadge phase="emerging" />);
    const pill = screen.getByText("Emerging");
    expect(pill).toHaveClass("text-phase-emerging");
    expect(pill).toHaveClass("bg-phase-emerging/15");
  });

  it("renders flash_event as 'Flash Event' with flash tint", () => {
    render(<PhaseBadge phase="flash_event" />);
    const pill = screen.getByText("Flash Event");
    expect(pill).toHaveClass("text-phase-flash");
  });

  it("falls back to raw phase key if unknown", () => {
    render(<PhaseBadge phase="unknown_phase" />);
    expect(screen.getByText("unknown_phase")).toBeInTheDocument();
  });
});
