import { Eyebrow, Rule } from "../ui";

interface ComingSoonPanelProps {
  title: string;
  description: string;
  phase?: string;
  eyebrow?: string;
}

export function ComingSoonPanel({ title, description, phase = "Phase 2", eyebrow = "Coming soon" }: ComingSoonPanelProps) {
  return (
    <section className="px-5 py-8 max-w-3xl">
      <Eyebrow>{eyebrow}</Eyebrow>
      <h1 className="text-[1.6rem] mt-1 mb-2">{title}</h1>
      <Rule />
      <p className="mt-3 text-[0.88rem] text-ink/85 max-w-prose">{description}</p>
      <div className="mt-5 border border-dashed border-ink/25 rounded-sm bg-ink/[0.02] p-4 flex flex-col gap-3">
        <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted">Upcoming</span>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted w-[3rem]">RT</span>
          <span className="flex-1 h-2 bg-ink/10 rounded-sm" />
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted w-[3rem]">Tass</span>
          <span className="flex-1 h-2 bg-ink/10 rounded-sm" style={{ width: "70%" }} />
        </div>
        <div className="flex items-center gap-3">
          <span className="font-mono text-[0.56rem] uppercase tracking-[0.1em] text-muted w-[3rem]">Reuters</span>
          <span className="flex-1 h-2 bg-ink/10 rounded-sm" style={{ width: "40%" }} />
        </div>
      </div>
      <div className="mt-4 inline-block font-mono text-[0.58rem] uppercase tracking-[0.12em] bg-ink text-paper rounded-sm px-2 py-1">
        {phase}
      </div>
    </section>
  );
}
