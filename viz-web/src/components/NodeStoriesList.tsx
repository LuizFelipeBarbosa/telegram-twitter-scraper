import { useState } from "react";
import type { NodeStoryRow } from "../lib/types";
import { Eyebrow } from "../ui";

interface NodeStoriesListProps {
  stories: NodeStoryRow[];
}

export function NodeStoriesList({ stories }: NodeStoriesListProps) {
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
        <Eyebrow>Recent stories</Eyebrow>
        <h2 className="text-[1.1rem] mt-0.5">Latest assignments</h2>
      </div>
      {stories.length === 0 ? (
        <p className="py-3 text-[0.78rem] text-muted">No stories for this node yet.</p>
      ) : (
        <ul className="list-none p-0 m-0">
          {stories.map((story) => {
            const isOpen = expanded.has(story.story_id);
            const start = new Date(story.timestamp_start);
            return (
              <li key={story.story_id} className="border-b border-ink/10 py-2">
                <button
                  type="button"
                  onClick={() => toggle(story.story_id)}
                  aria-expanded={isOpen}
                  className="w-full grid grid-cols-[5.5rem_1fr_auto] gap-3 items-baseline text-left bg-transparent border-0 cursor-pointer"
                >
                  <time className="font-mono text-[0.66rem] text-muted leading-tight">
                    {start.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                    <br />
                    {start.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                  </time>
                  <span className="text-[0.86rem] font-medium leading-snug">
                    {story.preview_text || "(media-only story)"}
                  </span>
                  <span className="font-mono text-[0.68rem] text-muted text-right whitespace-nowrap">
                    {story.channel_title} · {story.confidence.toFixed(2)}
                  </span>
                </button>
                {isOpen ? (
                  <div className="mt-2 pl-[6.5rem] pr-2 text-[0.82rem] text-ink/85">
                    <p className="m-0">{story.combined_text || "(media-only story)"}</p>
                    {story.media_refs.length > 0 ? (
                      <ul className="mt-1 pl-4 text-[0.72rem] text-muted list-disc">
                        {story.media_refs.map((media, index) => (
                          <li key={`${story.story_id}-media-${index}`}>
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
