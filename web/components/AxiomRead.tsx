"use client";

import { motion } from "motion/react";
import type { Insight } from "@/types/api";
import { pct, signedPct, odds } from "@/lib/format";

const LEAGUE_LABEL: Record<string, string> = {
  nba: "NBA",
  mlb: "MLB",
  nhl: "NHL",
};

export default function AxiomRead({ insight }: { insight: Insight }) {
  if (!insight.available) {
    return (
      <section className="rounded-md border border-border-subtle bg-surface px-6 py-8">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-text-tertiary">
          AXIOM Read
        </div>
        <p className="mt-3 text-sm text-text-secondary">
          No qualifying edge across today&apos;s slates. The model stays out when
          the market is fair. <span className="text-accent">∎</span>
        </p>
      </section>
    );
  }

  const stats = [
    { label: "Confidence", value: pct(insight.confidence ?? 0), tone: "text-text-primary" },
    { label: "Edge", value: signedPct(insight.edge ?? 0), tone: "text-pos" },
    { label: "EV / unit", value: signedPct(insight.ev_per_unit ?? 0), tone: "text-text-primary" },
    { label: "Kelly", value: pct(insight.kelly ?? 0), tone: "text-text-primary" },
  ];

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.26, ease: [0.23, 1, 0.32, 1] }}
      className="overflow-hidden rounded-md border border-border-strong bg-surface-elevated px-6 py-6"
    >
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-accent">
          AXIOM Read · highest conviction
        </div>
        <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-tertiary">
          {LEAGUE_LABEL[insight.league ?? ""]} moneyline
        </div>
      </div>

      <div className="mt-4 flex items-baseline gap-3">
        <h2 className="text-2xl font-semibold tracking-tight text-text-primary">
          {insight.pick}
        </h2>
        <span className="tnum text-base text-text-secondary">{odds(insight.price ?? null)}</span>
      </div>
      <p className="mt-0.5 text-sm text-text-secondary">{insight.matchup}</p>

      <p className="mt-4 max-w-2xl text-[13px] leading-relaxed text-text-secondary">
        {insight.rationale}
        {insight.line_movement ? (
          <span className="text-text-tertiary"> Market: {insight.line_movement}.</span>
        ) : null}
      </p>

      <div className="mt-5 grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="flex flex-col gap-1">
            <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-secondary">
              {s.label}
            </span>
            <span className={`tnum text-lg font-semibold ${s.tone}`}>{s.value}</span>
          </div>
        ))}
      </div>
    </motion.section>
  );
}
