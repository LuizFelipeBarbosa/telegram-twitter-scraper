import { describe, expect, it } from "vitest";
import { KIND_STROKE, KIND_LABEL } from "./kindColors";

describe("kindColors", () => {
  it("exposes a stroke color for every node kind", () => {
    expect(KIND_STROKE.event).toBe("#B45309");
    expect(KIND_STROKE.theme).toBe("#2F4858");
    expect(KIND_STROKE.person).toBe("#115E59");
    expect(KIND_STROKE.nation).toBe("#1D4ED8");
    expect(KIND_STROKE.org).toBe("#7C2D12");
    expect(KIND_STROKE.place).toBe("#4D7C0F");
  });

  it("exposes a human label for every node kind", () => {
    expect(KIND_LABEL.event).toBe("Event");
    expect(KIND_LABEL.theme).toBe("Theme");
    expect(KIND_LABEL.person).toBe("Person");
    expect(KIND_LABEL.nation).toBe("Nation");
    expect(KIND_LABEL.org).toBe("Organization");
    expect(KIND_LABEL.place).toBe("Place");
  });
});
