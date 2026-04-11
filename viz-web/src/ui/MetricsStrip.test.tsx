import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricCell } from "./MetricCell";
import { MetricsStrip } from "./MetricsStrip";

describe("MetricsStrip", () => {
  it("renders children in a grid with top and bottom ink rules", () => {
    const { container } = render(
      <MetricsStrip>
        <MetricCell label="A" value="1" />
        <MetricCell label="B" value="2" />
      </MetricsStrip>,
    );
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("B")).toBeInTheDocument();
    const strip = container.querySelector("[data-testid=\"metrics-strip\"]");
    expect(strip).toHaveClass("grid");
    expect(strip).toHaveClass("border-y");
  });
});
