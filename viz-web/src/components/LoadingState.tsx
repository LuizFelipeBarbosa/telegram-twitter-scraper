import { Eyebrow, Rule } from "../ui";

interface LoadingStateProps {
  view?: "landscape" | "node-detail";
}

export function LoadingState({ view = "landscape" }: LoadingStateProps) {
  const headline = view === "landscape" ? "Fetching landscape" : "Fetching node";
  return (
    <section className="px-5 py-8" role="status" aria-live="polite">
      <Eyebrow>Loading</Eyebrow>
      <h1 className="text-[1.6rem] mt-1 mb-2">{headline}</h1>
      <Rule />
      <div className="mt-4 h-2 w-full max-w-md bg-ink/10 overflow-hidden rounded-sm">
        <div className="h-full w-2/5 bg-phase-emerging animate-[slide_1.2s_ease-in-out_infinite]" />
      </div>
      <div className="mt-6 max-w-3xl">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="grid grid-cols-[0.6rem_1fr_4rem_4rem] gap-2 items-center py-2 border-b border-ink/10">
            <span className="w-[0.55rem] h-[0.55rem] rounded-full bg-ink/15" />
            <span className="h-2 bg-ink/10 rounded-sm" />
            <span className="h-2 bg-ink/10 rounded-sm" />
            <span className="h-2 bg-ink/10 rounded-sm" />
          </div>
        ))}
      </div>
      <span className="sr-only">Loading knowledge graph…</span>
      <style>{`
        @keyframes slide {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(260%); }
        }
      `}</style>
    </section>
  );
}
