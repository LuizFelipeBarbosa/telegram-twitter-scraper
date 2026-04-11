import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCell } from "./MetricCell";

describe("MetricCell", () => {
  it("renders label, value, and caption", () => {
    render(<MetricCell label="Nodes" value="184" caption="in 7d window" />);
    expect(screen.getByText("Nodes")).toBeInTheDocument();
    expect(screen.getByText("184")).toBeInTheDocument();
    expect(screen.getByText("in 7d window")).toBeInTheDocument();
  });

  it("renders value in mono font", () => {
    render(<MetricCell label="Heat" value="2.3" />);
    expect(screen.getByText("2.3")).toHaveClass("font-mono");
  });

  it("omits caption when not provided", () => {
    render(<MetricCell label="Relations" value="52" />);
    expect(screen.queryByText(/window/i)).toBeNull();
  });
});
