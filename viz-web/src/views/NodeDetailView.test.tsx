import { render, screen, within } from "@testing-library/react";
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
            parent_event: null,
            child_events: [
              {
                node_id: "event-2",
                slug: "tel-aviv-interception-strike",
                display_name: "Tel Aviv Interception Strike",
                summary: "Follow-on air defense activity over central Israel.",
                article_count: 1,
                child_count: 0,
                last_updated: "2026-04-09T08:00:00Z",
                event_start_at: "2026-04-09T07:30:00Z",
                primary_location: "Tel Aviv",
                location_labels: ["Tel Aviv"],
                organization_labels: ["Air Defense Command"],
              },
              {
                node_id: "event-3",
                slug: "haifa-port-strike",
                display_name: "Haifa Port Strike",
                summary: "A strike cluster around the port perimeter.",
                article_count: 4,
                child_count: 0,
                last_updated: "2026-04-08T08:00:00Z",
                event_start_at: "2026-04-08T07:45:00Z",
                primary_location: "Haifa",
                location_labels: ["Haifa"],
                organization_labels: ["Israeli Navy"],
              },
              {
                node_id: "event-4",
                slug: "tel-aviv-coordination-strike",
                display_name: "Tel Aviv Coordination Strike",
                summary: "Civil defense and response coordination after impact alerts.",
                article_count: 6,
                child_count: 0,
                last_updated: "2026-04-07T08:00:00Z",
                event_start_at: "2026-04-07T07:45:00Z",
                primary_location: "Tel Aviv",
                location_labels: ["Tel Aviv"],
                organization_labels: ["Home Front Command"],
              },
            ],
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
    if (input === "/api/nodes/event/operation-roaring-lion") {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            node_id: "event-legacy",
            kind: "event",
            slug: "operation-roaring-lion",
            display_name: "Operation Roaring Lion",
            summary: "Legacy API payload without hierarchy fields.",
            article_count: 3,
            events: [],
            people: [],
            nations: [],
            orgs: [],
            places: [],
            themes: [],
            stories: [
              {
                story_id: "story-legacy",
                channel_id: 7,
                channel_title: "Legacy Feed",
                timestamp_start: "2026-04-07T12:00:00Z",
                timestamp_end: "2026-04-07T12:02:00Z",
                confidence: 0.71,
                preview_text: "Legacy story preview",
                combined_text: "Legacy story body.",
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
  it("filters and sorts sub-events across the graph and browser", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/node/event/april-8-hormuz-reclosure"]}>
        <Routes>
          <Route path="/node/:kind/:slug" element={<NodeDetailView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "April 8 Hormuz Reclosure" })).toBeInTheDocument();
    expect(screen.getByText("Sub-event explorer")).toBeInTheDocument();
    const graphRegion = screen.getByRole("region", { name: "Sub-event graph" });
    const browserRegion = screen.getByRole("region", { name: "Sub-event browser" });
    expect(within(graphRegion).getByLabelText("Graph node: Tel Aviv Interception Strike")).toHaveAttribute(
      "href",
      "/node/event/tel-aviv-interception-strike",
    );
    expect(within(browserRegion).getAllByRole("link")[0]).toHaveTextContent("Tel Aviv Interception Strike");

    await user.selectOptions(screen.getByLabelText("Location filter"), "Tel Aviv");
    expect(within(browserRegion).queryByText("Haifa Port Strike")).not.toBeInTheDocument();
    expect(within(graphRegion).queryByLabelText("Graph node: Haifa Port Strike")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Sort sub-events"), "stories");
    expect(within(browserRegion).getAllByRole("link")[0]).toHaveTextContent("Tel Aviv Coordination Strike");

    await user.selectOptions(screen.getByLabelText("Organization filter"), "Home Front Command");
    expect(within(browserRegion).getByText("Tel Aviv Coordination Strike")).toBeInTheDocument();
    expect(within(browserRegion).queryByText("Tel Aviv Interception Strike")).not.toBeInTheDocument();
    expect(within(graphRegion).getByLabelText("Graph node: Tel Aviv Coordination Strike")).toBeInTheDocument();
    expect(within(graphRegion).queryByLabelText("Graph node: Tel Aviv Interception Strike")).not.toBeInTheDocument();

    await user.click(screen.getByText("Alpha story preview"));
    expect(await screen.findByText("Alpha story preview with the full body.")).toBeInTheDocument();
  });

  it("renders legacy event payloads that do not include hierarchy fields", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/node/event/operation-roaring-lion"]}>
        <Routes>
          <Route path="/node/:kind/:slug" element={<NodeDetailView />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { level: 1, name: "Operation Roaring Lion" })).toBeInTheDocument();
    expect(screen.queryByText("Sub-event explorer")).not.toBeInTheDocument();
    await user.click(screen.getByText("Legacy story preview"));
    expect(await screen.findByText("Legacy story body.")).toBeInTheDocument();
  });
});
