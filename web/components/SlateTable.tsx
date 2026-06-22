"use client";

import { useMemo, useState } from "react";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { CaretUp, CaretDown } from "@phosphor-icons/react";
import type { Game } from "@/types/api";
import { pct, signedPct, odds, tipET } from "@/lib/format";

// One row per game, framed around the side the model would back:
// the value side if there is one, otherwise the model's favorite.
type Row = {
  matchup: string;
  tip: string;
  pick: string;
  prob: number;
  fair: number;
  edge: number;
  price: number | null;
  isValue: boolean;
  flag: string;
};

function toRow(g: Game): Row {
  const side =
    g.home.is_value && !g.away.is_value
      ? g.home
      : g.away.is_value && !g.home.is_value
        ? g.away
        : g.home.model_prob >= g.away.model_prob
          ? g.home
          : g.away;
  return {
    matchup: `${g.away_team} @ ${g.home_team}`,
    tip: tipET(g.commence_time),
    pick: side.team,
    prob: side.model_prob,
    fair: side.fair_prob,
    edge: side.edge,
    price: side.price,
    isValue: side.is_value,
    flag: g.market_flag,
  };
}

const numHeader = "w-20 text-right";

export default function SlateTable({ games }: { games: Game[] }) {
  const data = useMemo(() => games.map(toRow), [games]);
  const [sorting, setSorting] = useState<SortingState>([{ id: "edge", desc: true }]);

  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        accessorKey: "pick",
        header: "Pick",
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="flex items-center gap-2">
              {r.isValue && <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />}
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-text-primary">{r.pick}</div>
                <div className="truncate text-[11px] text-text-tertiary">
                  {r.matchup} · {r.tip}
                  {r.flag ? ` · ${r.flag}` : ""}
                </div>
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: "prob",
        header: "Model",
        cell: ({ getValue }) => (
          <span className="tnum block text-right text-sm text-text-primary">
            {pct(getValue<number>())}
          </span>
        ),
      },
      {
        accessorKey: "fair",
        header: "Book",
        cell: ({ getValue }) => (
          <span className="tnum block text-right text-sm text-text-secondary">
            {pct(getValue<number>())}
          </span>
        ),
      },
      {
        accessorKey: "edge",
        header: "Edge",
        cell: ({ getValue }) => {
          const v = getValue<number>();
          return (
            <span
              className={`tnum block text-right text-sm font-semibold ${
                v > 0 ? "text-pos" : "text-text-tertiary"
              }`}
            >
              {signedPct(v)}
            </span>
          );
        },
      },
      {
        accessorKey: "price",
        header: "Line",
        enableSorting: false,
        cell: ({ getValue }) => (
          <span className="tnum block text-right text-sm text-text-secondary">
            {odds(getValue<number | null>())}
          </span>
        ),
      },
    ],
    [],
  );

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <div className="overflow-hidden rounded-md border border-border-subtle">
      <table className="w-full border-collapse">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="bg-surface">
              {hg.headers.map((h) => {
                const sortable = h.column.getCanSort();
                const sorted = h.column.getIsSorted();
                const isNum = h.column.id !== "pick";
                return (
                  <th
                    key={h.id}
                    onClick={sortable ? h.column.getToggleSortingHandler() : undefined}
                    className={`border-b border-border-subtle px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-tertiary ${
                      isNum ? numHeader : "text-left"
                    } ${sortable ? "cursor-pointer select-none [@media(hover:hover)]:hover:text-text-secondary" : ""}`}
                  >
                    <span className={`inline-flex items-center gap-1 ${isNum ? "justify-end" : ""}`}>
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {sorted === "asc" && <CaretUp weight="bold" className="text-accent" />}
                      {sorted === "desc" && <CaretDown weight="bold" className="text-accent" />}
                    </span>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, i) => (
            <tr
              key={row.id}
              className={`bg-surface transition-colors duration-[var(--dur-micro)] [@media(hover:hover)]:hover:bg-surface-elevated ${
                i > 0 ? "border-t border-border-subtle" : ""
              }`}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-5 py-3 align-middle">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
