"use client";

import { useMemo, useState } from "react";
import type { PropRow } from "@/types/api";
import { pct, signedPct, odds } from "@/lib/format";

// Projection vs line, normalized per row so different markets stay comparable.
function PredVsLine({ line, pred, side }: { line: number; pred: number; side: string }) {
  const max = Math.max(line, pred) * 1.3 || 1;
  const lx = (line / max) * 100;
  const px = (pred / max) * 100;
  const favorable = side === "Over" ? pred > line : pred < line;
  const lo = Math.min(lx, px);
  const hi = Math.max(lx, px);
  return (
    <div className="flex items-center gap-2.5">
      <div className="relative h-1.5 w-24 rounded-full bg-surface-overlay">
        <div
          className="absolute top-0 h-1.5 rounded-full"
          style={{ left: `${lo}%`, width: `${hi - lo}%`, background: favorable ? "var(--pos)" : "var(--neg)" }}
        />
        {/* line marker */}
        <div className="absolute -top-0.5 h-2.5 w-0.5 bg-text-secondary" style={{ left: `${lx}%` }} />
        {/* projection dot */}
        <div
          className="absolute -top-[3px] h-3 w-3 -translate-x-1/2 rounded-full border-2 border-bg"
          style={{ left: `${px}%`, background: favorable ? "var(--pos)" : "var(--neg)" }}
        />
      </div>
      <span className="tnum whitespace-nowrap text-[11px] text-text-tertiary">
        proj {pred.toFixed(1)} · line {line}
      </span>
    </div>
  );
}

function HeroCard({ p }: { p: PropRow }) {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-border-strong bg-surface-elevated px-5 py-4">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-tertiary">
          {p.market}
        </span>
        <span className="tnum rounded-full bg-surface px-2 py-0.5 text-[12px] text-text-secondary">
          {p.side} {p.line}
        </span>
      </div>
      <div>
        <div className="truncate text-base font-semibold text-text-primary">{p.player}</div>
        <div className="truncate text-[11px] text-text-tertiary">{p.matchup}</div>
      </div>
      <div className="flex items-end justify-between">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">Edge</span>
          <span className="tnum text-2xl font-semibold text-pos">{signedPct(p.edge)}</span>
        </div>
        <div className="flex gap-5 text-right">
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">Model</span>
            <span className="tnum text-sm text-text-primary">{pct(p.prob)}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">Proj</span>
            <span className="tnum text-sm text-text-primary">{p.pred.toFixed(1)}</span>
          </div>
          <div className="flex flex-col">
            <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">Line</span>
            <span className="tnum text-sm text-text-secondary">{odds(p.price)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function PropsBoard({ props: rows }: { props: PropRow[] }) {
  const markets = useMemo(() => {
    const counts = new Map<string, number>();
    for (const p of rows) counts.set(p.market, (counts.get(p.market) ?? 0) + 1);
    return Array.from(counts.entries());
  }, [rows]);

  const [tab, setTab] = useState<string>("All");
  const hero = rows.slice(0, 3);
  const list = tab === "All" ? rows : rows.filter((p) => p.market === tab);

  const tabs: [string, number][] = [["All", rows.length], ...markets];

  return (
    <div className="flex flex-col gap-8">
      {/* Best props */}
      <section>
        <h3 className="pb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
          Top conviction props
        </h3>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {hero.map((p, i) => (
            <HeroCard key={`${p.player}-${i}`} p={p} />
          ))}
        </div>
      </section>

      {/* Market tabs + list */}
      <section>
        <div className="flex flex-wrap gap-1 border-b border-border-subtle pb-3">
          {tabs.map(([m, n]) => {
            const active = tab === m;
            return (
              <button
                key={m}
                onClick={() => setTab(m)}
                className={`flex items-center gap-1.5 rounded-[8px] px-3 py-1.5 text-[13px] transition-colors duration-[var(--dur-micro)] ${
                  active
                    ? "bg-surface-elevated font-medium text-accent"
                    : "text-text-secondary [@media(hover:hover)]:hover:bg-surface [@media(hover:hover)]:hover:text-text-primary"
                }`}
              >
                {m}
                <span className="tnum text-[11px] text-text-tertiary">{n}</span>
              </button>
            );
          })}
        </div>

        <div className="mt-4 overflow-hidden rounded-md border border-border-subtle">
          <div className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 border-b border-border-subtle bg-surface px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-tertiary">
            <span>Player</span>
            <span className="w-48">Projection vs line</span>
            <span className="w-14 text-right">Model</span>
            <span className="w-16 text-right">Edge</span>
          </div>
          {list.map((p, i) => (
            <div
              key={`${p.player}-${p.market}-${i}`}
              className={`grid grid-cols-[1fr_auto_auto_auto] items-center gap-4 bg-surface px-5 py-3 ${
                i > 0 ? "border-t border-border-subtle" : ""
              }`}
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-text-primary">
                  {p.player}{" "}
                  <span className="text-[12px] font-normal text-text-tertiary">
                    · {p.side} {p.line} {p.market}
                  </span>
                </div>
                <div className="truncate text-[11px] text-text-tertiary">{p.matchup}</div>
              </div>
              <div className="w-48">
                <PredVsLine line={p.line} pred={p.pred} side={p.side} />
              </div>
              <span className="tnum w-14 text-right text-sm text-text-primary">{pct(p.prob)}</span>
              <span className="tnum w-16 text-right text-sm font-semibold text-pos">
                {signedPct(p.edge)}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
