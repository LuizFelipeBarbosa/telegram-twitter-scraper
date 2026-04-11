import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterBar } from "./FilterBar";

describe("FilterBar", () => {
  const phases = new Set(["emerging", "sustained"]);
  const kinds = new Set<"event" | "theme" | "person" | "nation" | "org" | "place">(["event", "theme"]);

  it("renders six kind chips", () => {
    render(
      <FilterBar
        kinds={kinds}
        phases={phases}
        onKindToggle={() => undefined}
        onPhaseToggle={() => undefined}
      />,
    );
    ["Event", "Theme", "Person", "Nation", "Organization", "Place"].forEach((label) => {
      expect(screen.getByRole("button", { name: new RegExp(label, "i") })).toBeInTheDocument();
    });
  });

  it("fires onKindToggle with the clicked kind", async () => {
    const handler = vi.fn();
    render(
      <FilterBar
        kinds={kinds}
        phases={phases}
        onKindToggle={handler}
        onPhaseToggle={() => undefined}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /person/i }));
    expect(handler).toHaveBeenCalledWith("person");
  });

  it("dims phase pills when theme is not in kinds", () => {
    const kindsWithoutTheme = new Set<"event" | "theme" | "person" | "nation" | "org" | "place">(["event"]);
    render(
      <FilterBar
        kinds={kindsWithoutTheme}
        phases={phases}
        onKindToggle={() => undefined}
        onPhaseToggle={() => undefined}
      />,
    );
    const phaseGroup = screen.getByTestId("phase-group");
    expect(phaseGroup).toHaveClass("opacity-40");
  });

  it("fires onPhaseToggle with the clicked phase", async () => {
    const handler = vi.fn();
    render(
      <FilterBar
        kinds={kinds}
        phases={phases}
        onKindToggle={() => undefined}
        onPhaseToggle={handler}
      />,
    );
    await userEvent.click(screen.getByText("Fading"));
    expect(handler).toHaveBeenCalledWith("fading");
  });
});
