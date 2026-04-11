import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { NodeDetailView } from "./NodeDetailView";

vi.stubGlobal(
  "fetch",
  vi.fn((input: string) => {
    if (input === "/api/nodes/event/april-8-hormuz-reclosure") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            node_id: "event-1",
            kind: "event",
            slug: "april-8-hormuz-reclosure",
            display_name: "April 8 Hormuz Reclosure",
            summary: "Node summary",
            article_count: 2,
            events: [],
            people: [],
            nations: [],
            orgs: [],
            places: [],
            themes: [],
            stories: [
              {
                story_id: "story-1",
                channel_id: 1,
                channel_title: "Signal Watch",
                timestamp_start: "2026-04-08T12:00:00Z",
                timestamp_end: "2026-04-08T12:03:00Z",
                confidence: 0.82,
                preview_text: "Alpha story preview",
                combined_text: "Alpha story preview with the full body.",
                media_refs: [],
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    }
    return Promise.reject(new Error(`Unexpected fetch: ${input}`));
  }),
);

describe("NodeDetailView", () => {
  it("expands a story row to reveal full text", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/node/event/april-8-hormuz-reclosure"]}>
        <Routes>
          <Route path="/node/:kind/:slug" element={<NodeDetailView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "April 8 Hormuz Reclosure" })).toBeInTheDocument();
    await user.click(screen.getByText("Alpha story preview"));
    expect(await screen.findByText("Alpha story preview with the full body.")).toBeInTheDocument();
  });
});
