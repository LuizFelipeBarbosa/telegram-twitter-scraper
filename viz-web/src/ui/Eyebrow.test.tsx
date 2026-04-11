import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Eyebrow } from "./Eyebrow";

describe("Eyebrow", () => {
  it("renders uppercase label with tracked letter spacing", () => {
    render(<Eyebrow>live topic landscape</Eyebrow>);
    const el = screen.getByText("live topic landscape");
    expect(el).toHaveClass("uppercase");
    expect(el).toHaveClass("tracking-[0.16em]");
    expect(el).toHaveClass("text-muted");
  });
});
