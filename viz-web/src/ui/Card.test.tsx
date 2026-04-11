import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "./Card";

describe("Card", () => {
  it("renders a cream card with children", () => {
    render(<Card>Hello</Card>);
    const card = screen.getByText("Hello");
    expect(card).toHaveClass("bg-card");
    expect(card).toHaveClass("border");
  });
});
