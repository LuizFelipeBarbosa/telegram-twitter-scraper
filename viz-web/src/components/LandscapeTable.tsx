import type { GraphNodeRow } from "../lib/types";
import { KIND_LABEL, KIND_STROKE, SortableTable, type ColumnDef } from "../ui";

const PHASE_COLOR: Record<string, string> = {
  emerging: "#C94F2B",
  flash_event: "#D97706",
  sustained: "#0D7C66",
  fading: "#2F6FB5",
  steady: "#5C4A39",
};

interface LandscapeTableProps {
  nodes: GraphNodeRow[];
  hoveredNodeId: string | null;
  onHover: (nodeId: string | null) => void;
  onRowClick: (node: GraphNodeRow) => void;
  className?: string;
}

function dotColor(node: GraphNodeRow): string {
  if (node.kind === "theme" && node.phase) {
    return PHASE_COLOR[String(node.phase)] ?? KIND_STROKE.theme;
  }
  return KIND_STROKE[node.kind];
}

export function LandscapeTable({ nodes, hoveredNodeId, onHover, onRowClick, className }: LandscapeTableProps) {
  const columns: ColumnDef<GraphNodeRow>[] = [
    {
      key: "dot",
      header: "",
      width: "0.75rem",
      render: (node) => (
        <span
          aria-hidden="true"
          className="inline-block w-[0.55rem] h-[0.55rem] rounded-full"
          style={{ backgroundColor: dotColor(node) }}
        />
      ),
    },
    {
      key: "name",
      header: "Node",
      sortable: true,
      sortValue: (node) => node.display_name.toLowerCase(),
      render: (node) => (
        <div>
          <div className="font-medium">{node.display_name}</div>
          <div className="text-[0.68rem] text-muted mt-0.5">
            {KIND_LABEL[node.kind]}
            {node.kind === "theme" && node.phase ? <> · {String(node.phase).replace("_", " ")}</> : null}
            {node.kind === "event" && node.child_count > 0 ? <> · {node.child_count} sub-events</> : null}
            {node.summary ? (
              <>
                {" · "}
                <span className="italic">
                  {node.summary.length > 60 ? `${node.summary.slice(0, 60)}…` : node.summary}
                </span>
              </>
            ) : null}
          </div>
        </div>
      ),
    },
    {
      key: "score",
      header: "Score",
      numeric: true,
      sortable: true,
      sortValue: (node) => node.score,
      render: (node) => node.score.toFixed(2),
    },
    {
      key: "stories",
      header: "Stories",
      numeric: true,
      sortable: true,
      sortValue: (node) => node.article_count,
      render: (node) => node.article_count,
    },
    {
      key: "heat",
      header: "Heat",
      numeric: true,
      sortable: true,
      sortValue: (node) => node.heat ?? -Infinity,
      render: (node) => (node.heat != null ? node.heat.toFixed(3) : "—"),
    },
  ];

  return (
    <SortableTable
      className={className}
      columns={columns}
      rows={nodes}
      getRowId={(node) => node.node_id}
      initialSort={{ key: "score", dir: "desc" }}
      onRowClick={onRowClick}
      onRowHover={onHover}
      hoveredRowId={hoveredNodeId}
    />
  );
}
