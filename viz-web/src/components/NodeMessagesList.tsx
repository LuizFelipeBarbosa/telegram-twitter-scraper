import { useState } from "react";
import type { NodeMessageRow } from "../lib/types";
import { Eyebrow } from "../ui";

interface NodeMessagesListProps {
  messages: NodeMessageRow[];
}

export function NodeMessagesList({ messages }: NodeMessagesListProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (id: string) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <section>
      <div className="border-b border-ink pb-2 mb-1">
        <Eyebrow>Recent messages</Eyebrow>
        <h2 className="text-[1.1rem] mt-0.5">Latest assignments</h2>
      </div>
      {messages.length === 0 ? (
        <p className="py-3 text-[0.78rem] text-muted">No messages for this node yet.</p>
      ) : (
        <ul className="list-none p-0 m-0">
          {messages.map((message) => {
            const rowId = `${message.channel_id}:${message.message_id}`;
            const isOpen = expanded.has(rowId);
            const ts = new Date(message.timestamp);
            const displayText = message.english_text || message.text;
            return (
              <li key={rowId} className="border-b border-ink/10 py-2">
                <button
                  type="button"
                  onClick={() => toggle(rowId)}
                  aria-expanded={isOpen}
                  className="w-full grid grid-cols-[5.5rem_1fr_auto] gap-3 items-baseline text-left bg-transparent border-0 cursor-pointer"
                >
                  <time className="font-mono text-[0.66rem] text-muted leading-tight">
                    {ts.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    <br />
                    {ts.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </time>
                  <span className="text-[0.86rem] font-medium leading-snug">
                    {displayText || "(media-only message)"}
                  </span>
                  <span className="font-mono text-[0.68rem] text-muted text-right whitespace-nowrap">
                    {message.channel_title} · {message.confidence.toFixed(2)}
                  </span>
                </button>
                {isOpen ? (
                  <div className="mt-2 pl-[6.5rem] pr-2 text-[0.82rem] text-ink/85">
                    <p className="m-0 mb-1 font-mono text-[0.68rem] text-muted">{rowId}</p>
                    <p className="m-0">{displayText || "(media-only message)"}</p>
                    {message.media_refs.length > 0 ? (
                      <ul className="mt-1 pl-4 text-[0.72rem] text-muted list-disc">
                        {message.media_refs.map((media, index) => (
                          <li key={`${rowId}-media-${index}`}>
                            {media.file_name ?? media.storage_path ?? media.media_type}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
