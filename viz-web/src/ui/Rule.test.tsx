import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Rule } from "./Rule";

describe("Rule", () => {
  it("renders a bold ink hr by default", () => {
    const { container } = render(<Rule />);
    const hr = container.querySelector("hr");
    expect(hr).not.toBeNull();
    expect(hr).toHaveClass("border-ink");
  });

  it("renders a thin variant with muted border", () => {
    const { container } = render(<Rule variant="thin" />);
    const hr = container.querySelector("hr");
    expect(hr).toHaveClass("border-ink/20");
  });

  it("renders dashed variant", () => {
    const { container } = render(<Rule variant="dashed" />);
    const hr = container.querySelector("hr");
    expect(hr).toHaveClass("border-dashed");
  });
});
