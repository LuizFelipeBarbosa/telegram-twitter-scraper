import { Link } from "react-router-dom";
import type { EventHierarchyRef } from "../lib/types";

interface BreadcrumbsProps {
  kind: string;
  displayName: string;
  parentEvent?: EventHierarchyRef | null;
}

export function Breadcrumbs({ kind, displayName, parentEvent }: BreadcrumbsProps) {
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
      {parentEvent ? (
        <>
          <span aria-hidden="true">›</span>
          <Link
            to={`/node/event/${parentEvent.slug}`}
            className="text-ink underline underline-offset-[3px] decoration-ink/25 hover:decoration-ink/60"
          >
            {parentEvent.display_name}
          </Link>
        </>
      ) : null}
      <span aria-hidden="true">›</span>
      <span>{displayName}</span>
    </nav>
  );
}
