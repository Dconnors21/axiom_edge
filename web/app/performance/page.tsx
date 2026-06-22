import type { Metadata } from "next";
import type { League, Performance } from "@/types/api";
import { getPerformance } from "@/lib/api";
import { pct, signedPct } from "@/lib/format";
import CalibrationChart from "@/components/charts/CalibrationChart";
import RocChart from "@/components/charts/RocChart";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Model Performance" };

const LEAGUES: League[] = ["nba", "mlb", "nhl"];
const LABEL: Record<League, string> = { nba: "NBA", mlb: "MLB", nhl: "NHL" };

function Metric({
  label,
  value,
  tone = "text-text-primary",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-secondary">
        {label}
      </span>
      <span className={`tnum text-xl font-semibold ${tone}`}>{value}</span>
    </div>
  );
}

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-border-subtle bg-surface px-5 pb-4 pt-4">
      <div className="pb-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-secondary">
        {title}
      </div>
      {children}
    </div>
  );
}

function LeagueSection({ perf }: { perf: Performance }) {
  const record = perf.record_n > 0 ? `${perf.wins}–${perf.losses}` : "—";
  return (
    <section className="flex flex-col gap-5">
      <div className="flex items-baseline justify-between border-b border-border-subtle pb-3">
        <h2 className="text-lg font-semibold tracking-tight text-text-primary">
          {LABEL[perf.league]}
        </h2>
        <span className="text-[12px] text-text-tertiary">{perf.note}</span>
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4 lg:grid-cols-6">
        <Metric
          label="ROC-AUC (train)"
          value={perf.training_auc != null ? perf.training_auc.toFixed(4) : "—"}
          tone="text-accent"
        />
        <Metric
          label="ROC-AUC (live)"
          value={perf.empirical_auc != null ? perf.empirical_auc.toFixed(4) : "—"}
        />
        <Metric label="Brier" value={perf.brier != null ? perf.brier.toFixed(4) : "—"} />
        <Metric
          label="Log loss"
          value={perf.log_loss != null ? perf.log_loss.toFixed(4) : "—"}
        />
        <Metric label="Graded games" value={String(perf.graded_n)} />
        <Metric label="Bet record" value={record} />
      </div>

      {perf.sufficient ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ChartPanel title="Reliability: predicted vs actual">
            <CalibrationChart data={perf.calibration} />
          </ChartPanel>
          <ChartPanel title="ROC curve">
            <RocChart data={perf.roc} />
          </ChartPanel>
        </div>
      ) : (
        <div className="rounded-md border border-border-subtle bg-surface px-5 py-6">
          <p className="text-sm text-text-secondary">
            Not enough graded games to plot reliability yet ({perf.graded_n} logged).
          </p>
          <p className="mt-1 text-[13px] text-text-tertiary">
            The training ROC-AUC stands; live calibration appears once the sample is
            meaningful. <span className="text-accent">∎</span>
          </p>
        </div>
      )}
    </section>
  );
}

export default async function ModelPerformance() {
  const results = await Promise.allSettled(LEAGUES.map(getPerformance));
  const perfs = results
    .filter((r): r is PromiseFulfilledResult<Performance> => r.status === "fulfilled")
    .map((r) => r.value);

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="border-b border-border-subtle pb-5">
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          Model Performance
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Calibration and discrimination, evaluated on realized outcomes. Numbers are shown
          as they are.
        </p>
      </header>

      <div className="mt-10 flex flex-col gap-12">
        {perfs.map((p) => (
          <LeagueSection key={p.league} perf={p} />
        ))}
      </div>
    </div>
  );
}
