import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { NodeMessagesList } from "./NodeMessagesList";
import type { NodeMessageRow } from "../lib/types";

const messages: NodeMessageRow[] = [
  {
    channel_id: 1,
    message_id: 42,
    channel_title: "Signal Watch",
    timestamp: "2026-04-10T14:22:00Z",
    confidence: 0.87,
    text: "Primary challenger launches campaign",
    english_text: "Primary challenger launches campaign",
    media_refs: [],
  },
];

describe("NodeMessagesList", () => {
  it("renders a row per message with text + confidence", () => {
    render(<NodeMessagesList messages={messages} />);
    expect(screen.getByText("Primary challenger launches campaign")).toBeInTheDocument();
    expect(screen.getByText(/0\.87/)).toBeInTheDocument();
    expect(screen.getByText(/Signal Watch/)).toBeInTheDocument();
  });

  it("expands a row to show full text and message id when clicked", async () => {
    render(<NodeMessagesList messages={messages} />);
    await userEvent.click(screen.getByText("Primary challenger launches campaign"));
    expect(screen.getByText("1:42")).toBeInTheDocument();
  });

  it("renders empty state when messages is empty", () => {
    render(<NodeMessagesList messages={[]} />);
    expect(screen.getByText(/no messages/i)).toBeInTheDocument();
  });
});
