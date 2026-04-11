import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pill } from "./Pill";

describe("Pill", () => {
  it("renders a squared pill with uppercase text", () => {
    render(<Pill>Emerging</Pill>);
    const pill = screen.getByText("Emerging");
    expect(pill).toHaveClass("uppercase");
    expect(pill).toHaveClass("rounded-sm");
  });

  it("accepts custom tint classes via className", () => {
    render(<Pill className="bg-phase-emerging/15 text-phase-emerging">Emerging</Pill>);
    const pill = screen.getByText("Emerging");
    expect(pill).toHaveClass("bg-phase-emerging/15");
    expect(pill).toHaveClass("text-phase-emerging");
  });
});
