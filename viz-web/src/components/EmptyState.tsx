import { Button, Card, Eyebrow, Rule } from "../ui";

interface EmptyStateSuggestion {
  label: string;
  onClick: () => void;
}

interface EmptyStateProps {
  title: string;
  message: string;
  suggestions?: EmptyStateSuggestion[];
  onReset?: () => void;
}

export function EmptyState({ title, message, suggestions, onReset }: EmptyStateProps) {
  return (
    <section className="px-5 py-8">
      <Eyebrow>Nothing found</Eyebrow>
      <h1 className="text-[1.6rem] mt-1 mb-2">{title}</h1>
      <Rule />
      <p className="mt-3 text-[0.88rem] text-ink/85 max-w-prose">{message}</p>
      {suggestions && suggestions.length > 0 ? (
        <Card className="mt-5 max-w-md">
          <div className="font-mono text-[0.64rem] uppercase tracking-[0.1em] text-muted mb-2">/ suggestions</div>
          <ul className="list-none p-0 m-0 space-y-1">
            {suggestions.map((s) => (
              <li key={s.label}>
                <button
                  type="button"
                  onClick={s.onClick}
                  className="text-[0.82rem] text-ink underline underline-offset-2 decoration-ink/25 hover:decoration-ink/60 bg-transparent border-0 cursor-pointer p-0"
                >
                  <span className="text-phase-emerging mr-1">·</span>
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
          {onReset ? (
            <div className="mt-3">
              <Button variant="ghost" onClick={onReset}>
                Reset filters
              </Button>
            </div>
          ) : null}
        </Card>
      ) : null}
    </section>
  );
}
