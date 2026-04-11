import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SortableTable, type ColumnDef } from "./SortableTable";

interface Row {
  id: string;
  name: string;
  score: number;
}

const rows: Row[] = [
  { id: "1", name: "Alpha", score: 10 },
  { id: "2", name: "Bravo", score: 30 },
  { id: "3", name: "Charlie", score: 20 },
];

const columns: ColumnDef<Row>[] = [
  { key: "name", header: "Name", render: (row) => row.name },
  { key: "score", header: "Score", render: (row) => row.score, numeric: true, sortable: true },
];

describe("SortableTable", () => {
  it("renders rows in initial order", () => {
    render(<SortableTable columns={columns} rows={rows} getRowId={(r) => r.id} />);
    const cells = screen.getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent);
    expect(cells).toEqual(["Alpha", "Bravo", "Charlie"]);
  });

  it("sorts descending by default when column header is clicked", async () => {
    render(
      <SortableTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        initialSort={{ key: "score", dir: "desc" }}
      />,
    );
    const cells = screen.getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent);
    expect(cells).toEqual(["Bravo", "Charlie", "Alpha"]);
  });

  it("toggles sort direction when a sortable header is clicked", async () => {
    render(
      <SortableTable
        columns={columns}
        rows={rows}
        getRowId={(r) => r.id}
        initialSort={{ key: "score", dir: "desc" }}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Score/ }));
    const cells = screen.getAllByRole("row").slice(1).map((row) => row.querySelector("td")?.textContent);
    expect(cells).toEqual(["Alpha", "Charlie", "Bravo"]);
  });

  it("fires onRowClick with the row", async () => {
    const handler = vi.fn();
    render(<SortableTable columns={columns} rows={rows} getRowId={(r) => r.id} onRowClick={handler} />);
    await userEvent.click(screen.getByText("Bravo"));
    expect(handler).toHaveBeenCalledWith(rows[1]);
  });
});
