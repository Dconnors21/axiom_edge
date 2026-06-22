import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { League } from "@/types/api";
import { getRoi } from "@/lib/api";
import { pct, signedPct, signed, odds } from "@/lib/format";
import EquityChart from "@/components/charts/EquityChart";

export const dynamic = "force-dynamic";

const LEAGUES: League[] = ["nba", "mlb", "nhl"];
const LABEL: Record<League, string> = { nba: "NBA", mlb: "MLB", nhl: "NHL" };
const isLeague = (v: string): v is League => (LEAGUES as string[]).includes(v);

export async function generateMetadata({
  params,
}: {
  params: Promise<{ league: string }>;
}): Promise<Metadata> {
  const { league } = await params;
  return { title: isLeague(league) ? `${LABEL[league]} ROI` : "Not found" };
}

function Metric({ label, value, tone = "text-text-primary" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-secondary">{label}</span>
      <span className={`tnum text-xl font-semibold ${tone}`}>{value}</span>
    </div>
  );
}

export default async function RoiTracker({ params }: { params: Promise<{ league: string }> }) {
  const { league } = await params;
  if (!isLeague(league)) notFound();

  const roi = await getRoi(league);
  const profitTone = roi.units_profit > 0 ? "text-pos" : roi.units_profit < 0 ? "text-neg" : "text-text-primary";

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="border-b border-border-subtle pb-5">
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">{LABEL[league]} ROI Tracker</h1>
        <p className="mt-1 text-sm text-text-secondary">Realized results on logged bets, flat 1-unit basis.</p>
      </header>

      {roi.n_bets === 0 ? (
        <div className="mt-10 rounded-md border border-border-subtle bg-surface px-6 py-10 text-center">
          <p className="text-sm text-text-secondary">No logged bets yet.</p>
          <p className="mt-1 text-[13px] text-text-tertiary">
            Results appear here once bets are graded. <span className="text-accent">∎</span>
          </p>
        </div>
      ) : (
        <div className="mt-8 flex flex-col gap-9">
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
            <Metric label="Bets" value={String(roi.n_bets)} />
            <Metric label="Record" value={`${roi.wins}–${roi.losses}${roi.pushes ? `–${roi.pushes}` : ""}`} />
            <Metric label="Win rate" value={roi.win_rate != null ? pct(roi.win_rate) : "—"} />
            <Metric label="Units" value={`${signed(roi.units_profit)}u`} tone={profitTone} />
            <Metric label="ROI / bet" value={roi.roi != null ? signedPct(roi.roi) : "—"} tone={profitTone} />
            <Metric label="CLV" value={roi.clv_avg != null ? signedPct(roi.clv_avg) : "—"} />
          </div>

          {roi.equity.length > 1 && (
            <section>
              <h3 className="pb-2 text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
                Equity curve
              </h3>
              <div className="rounded-md border border-border-subtle bg-surface px-5 pb-4 pt-4">
                <EquityChart data={roi.equity} />
              </div>
            </section>
          )}

          <section>
            <h3 className="pb-3 text-[11px] font-bold uppercase tracking-[0.12em] text-text-secondary">
              Bet log
            </h3>
            <div className="overflow-hidden rounded-md border border-border-subtle">
              <div className="grid grid-cols-[auto_1fr_auto_auto_auto] gap-4 border-b border-border-subtle bg-surface px-5 py-2.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-text-tertiary">
                <span className="w-20">Date</span>
                <span>Pick</span>
                <span className="w-16 text-right">Edge</span>
                <span className="w-14 text-right">Result</span>
                <span className="w-16 text-right">P/L</span>
              </div>
              {roi.bets.map((b, i) => {
                const win = b.result.toUpperCase().startsWith("W");
                const loss = b.result.toUpperCase().startsWith("L");
                return (
                  <div
                    key={`${b.date}-${b.pick}-${i}`}
                    className={`grid grid-cols-[auto_1fr_auto_auto_auto] items-center gap-4 bg-surface px-5 py-2.5 ${
                      i > 0 ? "border-t border-border-subtle" : ""
                    }`}
                  >
                    <span className="tnum w-20 text-[12px] text-text-tertiary">{b.date}</span>
                    <div className="min-w-0">
                      <div className="truncate text-sm text-text-primary">
                        {b.pick} <span className="tnum text-text-tertiary">{odds(b.line)}</span>
                      </div>
                      <div className="truncate text-[11px] text-text-tertiary">{b.matchup}</div>
                    </div>
                    <span className="tnum w-16 text-right text-[13px] text-text-secondary">
                      {b.edge != null ? signedPct(b.edge) : "—"}
                    </span>
                    <span
                      className={`tnum w-14 text-right text-[13px] font-medium ${
                        win ? "text-pos" : loss ? "text-neg" : "text-text-tertiary"
                      }`}
                    >
                      {b.result}
                    </span>
                    <span
                      className={`tnum w-16 text-right text-[13px] ${
                        b.profit == null ? "text-text-tertiary" : b.profit >= 0 ? "text-pos" : "text-neg"
                      }`}
                    >
                      {b.profit != null ? `${signed(b.profit)}u` : "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
