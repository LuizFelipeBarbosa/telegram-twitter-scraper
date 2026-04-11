import { Link } from "react-router-dom";

interface BreadcrumbsProps {
  kind: string;
  displayName: string;
}

export function Breadcrumbs({ kind, displayName }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumbs" className="px-5 pt-3 text-[0.7rem] text-muted flex items-center gap-2">
      <Link
        to="/"
        className="text-ink underline underline-offset-[3px] decoration-ink/25 hover:decoration-ink/60"
      >
        Landscape
      </Link>
      <span aria-hidden="true">›</span>
      <span className="font-mono">{kind}</span>
      <span aria-hidden="true">›</span>
      <span>{displayName}</span>
    </nav>
  );
}
