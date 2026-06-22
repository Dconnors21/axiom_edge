"use client";

import { useState } from "react";
import { TrendUp, TrendDown, Minus } from "@phosphor-icons/react";
import type { ResearchDetail } from "@/types/api";
import GameBars from "@/components/charts/GameBars";

const fmt = (v: number) => (v % 1 === 0 ? String(v) : v.toFixed(1));
const matchup = (opp: string, home: boolean) =>
  opp ? `${home ? "vs" : "@"} ${opp}` : home ? "Home" : "Away";

function SummaryTile({ label, value, trend }: { label: string; value: string; trend?: number }) {
  const up = trend != null && trend > 0.05;
  const down = trend != null && trend < -0.05;
  const Icon = up ? TrendUp : down ? TrendDown : Minus;
  const tone = up ? "text-pos" : down ? "text-neg" : "text-text-tertiary";
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-medium uppercase tracking-[0.06em] text-text-secondary">
        {label}
      </span>
      <span className="tnum inline-flex items-center gap-1.5 text-lg font-semibold text-text-primary">
        {value}
        {trend != null && <Icon weight="bold" className={`text-[13px] ${tone}`} />}
      </span>
    </div>
  );
}

export default function PlayerCard({ detail }: { detail: ResearchDetail }) {
  const [stat, setStat] = useState(detail.stat_keys[0]);

  const series = detail.games.map((g) => g.stats[stat] ?? 0);
  const avg = detail.averages[stat] ?? 0;
  const last3 = detail.recent[stat] ?? 0;
  const high = series.length ? Math.max(...series) : 0;
  const low = series.length ? Math.min(...series) : 0;
  const aboveAvg = series.filter((v) => v >= avg).length;

  const bars = detail.games.map((g) => ({
    label: g.opponent || (g.home ? "H" : "A"),
    value: g.stats[stat] ?? 0,
  }));

  const logRows = [...detail.games].reverse();

  return (
    <div className="rounded-md border border-border-strong bg-surface-elevated">
      {/* Header */}
      <div className="flex items-baseline justify-between border-b border-border-subtle px-6 py-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-text-primary">{detail.player}</h2>
          <p className="mt-0.5 text-[12px] text-text-tertiary">
            {detail.team} · last {detail.games.length} games
          </p>
        </div>
        {/* Stat selector */}
        <div className="flex gap-1">
          {detail.stat_keys.map((k) => {
            const active = k === stat;
            return (
              <button
                key={k}
                onClick={() => setStat(k)}
                className={`rounded-[8px] px-2.5 py-1 text-[12px] font-medium transition-colors duration-[var(--dur-micro)] ${
                  active
                    ? "bg-surface text-accent"
                    : "text-text-tertiary [@media(hover:hover)]:hover:text-text-secondary"
                }`}
              >
                {k}
              </button>
            );
          })}
        </div>
      </div>

      {/* Featured chart for the selected stat */}
      <div className="px-5 pt-4">
        <GameBars data={bars} avg={avg} />
      </div>

      {/* Summary for the selected stat */}
      <div className="grid grid-cols-2 gap-y-4 px-6 py-4 sm:grid-cols-4">
        <SummaryTile label={`${stat} avg`} value={fmt(Number(avg.toFixed(1)))} />
        <SummaryTile label="Last 3" value={fmt(Number(last3.toFixed(1)))} trend={last3 - avg} />
        <SummaryTile label="High" value={fmt(high)} />
        <SummaryTile label="Low" value={fmt(low)} />
      </div>
      <p className="border-b border-border-subtle px-6 pb-4 text-[12px] text-text-tertiary">
        <span className="tnum text-text-secondary">
          {aboveAvg} of {series.length}
        </span>{" "}
        games at or above the {stat} average.
      </p>

      {/* Game log */}
      <div className="px-6 py-4">
        <h3 className="pb-2 text-[10px] font-bold uppercase tracking-[0.12em] text-text-tertiary">
          Game log
        </h3>
        <div className="overflow-hidden rounded-md border border-border-subtle">
          <div
            className="grid items-center gap-3 border-b border-border-subtle bg-surface px-4 py-2 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-tertiary"
            style={{ gridTemplateColumns: `4rem 1fr repeat(${detail.stat_keys.length}, 2.75rem)` }}
          >
            <span>Date</span>
            <span>Matchup</span>
            {detail.stat_keys.map((k) => (
              <span key={k} className="text-right">
                {k}
              </span>
            ))}
          </div>
          {logRows.map((g, i) => (
            <div
              key={`${g.date}-${i}`}
              className={`grid items-center gap-3 bg-surface px-4 py-2 ${
                i > 0 ? "border-t border-border-subtle" : ""
              }`}
              style={{ gridTemplateColumns: `4rem 1fr repeat(${detail.stat_keys.length}, 2.75rem)` }}
            >
              <span className="tnum text-[12px] text-text-tertiary">{g.date.slice(5)}</span>
              <span className="truncate text-[12px] text-text-secondary">
                {matchup(g.opponent, g.home)}
              </span>
              {detail.stat_keys.map((k) => {
                const v = g.stats[k] ?? 0;
                const hot = k === stat && v >= (detail.averages[k] ?? 0);
                return (
                  <span
                    key={k}
                    className={`tnum text-right text-[12px] ${
                      hot ? "font-semibold text-accent" : "text-text-primary"
                    }`}
                  >
                    {fmt(v)}
                  </span>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
