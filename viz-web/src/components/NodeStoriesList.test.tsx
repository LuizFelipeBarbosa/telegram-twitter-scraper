import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { NodeStoriesList } from "./NodeStoriesList";
import type { NodeStoryRow } from "../lib/types";

const stories: NodeStoryRow[] = [
  {
    story_id: "s-1",
    channel_id: 1,
    channel_title: "Signal Watch",
    timestamp_start: "2026-04-10T14:22:00Z",
    timestamp_end: "2026-04-10T14:25:00Z",
    confidence: 0.87,
    preview_text: "Primary challenger launches campaign",
    combined_text: "Full body: Primary challenger launches campaign with focus on border policy.",
    media_refs: [],
  },
];

describe("NodeStoriesList", () => {
  it("renders a row per story with preview + confidence", () => {
    render(<NodeStoriesList stories={stories} />);
    expect(screen.getByText("Primary challenger launches campaign")).toBeInTheDocument();
    expect(screen.getByText(/0\.87/)).toBeInTheDocument();
    expect(screen.getByText(/Signal Watch/)).toBeInTheDocument();
  });

  it("expands a row to show combined_text when clicked", async () => {
    render(<NodeStoriesList stories={stories} />);
    await userEvent.click(screen.getByText("Primary challenger launches campaign"));
    expect(
      screen.getByText(/Full body: Primary challenger launches campaign with focus on border policy\./),
    ).toBeInTheDocument();
  });

  it("renders empty state when stories is empty", () => {
    render(<NodeStoriesList stories={[]} />);
    expect(screen.getByText(/no stories/i)).toBeInTheDocument();
  });
});
