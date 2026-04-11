import { clsx } from "clsx";
import { useMemo, useState, type ReactNode } from "react";

export interface ColumnDef<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  numeric?: boolean;
  sortable?: boolean;
  sortValue?: (row: Row) => number | string;
  width?: string;
}

interface SortState {
  key: string;
  dir: "asc" | "desc";
}

interface SortableTableProps<Row> {
  columns: ColumnDef<Row>[];
  rows: Row[];
  getRowId: (row: Row) => string;
  initialSort?: SortState;
  onRowClick?: (row: Row) => void;
  onRowHover?: (rowId: string | null) => void;
  hoveredRowId?: string | null;
  className?: string;
}

export function SortableTable<Row>({
  columns,
  rows,
  getRowId,
  initialSort,
  onRowClick,
  onRowHover,
  hoveredRowId,
  className,
}: SortableTableProps<Row>) {
  const [sort, setSort] = useState<SortState | null>(initialSort ?? null);

  const sorted = useMemo(() => {
    if (!sort) {
      return rows;
    }
    const col = columns.find((column) => column.key === sort.key);
    if (!col) {
      return rows;
    }
    const value = col.sortValue ?? ((row: Row) => {
      const rendered = col.render(row);
      if (typeof rendered === "number" || typeof rendered === "string") {
        return rendered;
      }
      return "";
    });
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = value(a);
      const bv = value(b);
      if (typeof av === "number" && typeof bv === "number") {
        return sort.dir === "asc" ? av - bv : bv - av;
      }
      return sort.dir === "asc"
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
    return copy;
  }, [columns, rows, sort]);

  const toggleSort = (key: string) => {
    setSort((previous) => {
      if (!previous || previous.key !== key) {
        return { key, dir: "desc" };
      }
      return { key, dir: previous.dir === "desc" ? "asc" : "desc" };
    });
  };

  return (
    <table className={clsx("w-full border-collapse text-[0.78rem]", className)}>
      <thead>
        <tr>
          {columns.map((column) => {
            const isSorted = sort?.key === column.key;
            const sortable = column.sortable ?? column.numeric ?? false;
            return (
              <th
                key={column.key}
                scope="col"
                aria-sort={isSorted ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                onClick={sortable ? () => toggleSort(column.key) : undefined}
                className={clsx(
                  "text-[0.56rem] uppercase tracking-[0.1em] text-muted font-semibold py-2 px-1 border-b border-ink text-left",
                  column.numeric && "text-right",
                  sortable && "cursor-pointer select-none hover:text-ink",
                )}
                style={column.width ? { width: column.width } : undefined}
              >
                {column.header}
                {isSorted ? <span aria-hidden="true">{sort!.dir === "asc" ? " ↑" : " ↓"}</span> : null}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => {
          const rowId = getRowId(row);
          const hovered = hoveredRowId === rowId;
          return (
            <tr
              key={rowId}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              onMouseEnter={onRowHover ? () => onRowHover(rowId) : undefined}
              onMouseLeave={onRowHover ? () => onRowHover(null) : undefined}
              className={clsx(
                "border-b border-ink/10 align-middle transition-colors",
                onRowClick && "cursor-pointer",
                hovered && "bg-phase-emerging/5",
              )}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={clsx("py-2 px-1", column.numeric && "text-right font-mono")}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
