import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThemeHistory } from "./ThemeHistory";
import type { ThemeHistoryPoint } from "../lib/types";

const history: ThemeHistoryPoint[] = [
  { date: "2026-04-08T00:00:00Z", article_count: 12, centroid_drift: 0.11 },
  { date: "2026-04-09T00:00:00Z", article_count: 18, centroid_drift: 0.14 },
];

describe("ThemeHistory", () => {
  it("renders section header", () => {
    render(<ThemeHistory history={history} />);
    expect(screen.getByText(/volume and drift/i)).toBeInTheDocument();
    expect(screen.getByText(/theme evolution/i)).toBeInTheDocument();
  });

  it("renders an empty placeholder when history is empty", () => {
    render(<ThemeHistory history={[]} />);
    expect(screen.getByText(/no history yet/i)).toBeInTheDocument();
  });
});
