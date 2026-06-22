"use client";

import { useEffect, useState } from "react";
import type { EVResponse } from "@/types/api";
import { postEv } from "@/lib/api";
import { pct, signedPct } from "@/lib/format";

function Field({
  label,
  suffix,
  value,
  onChange,
  step = "1",
}: {
  label: string;
  suffix?: string;
  value: string;
  onChange: (v: string) => void;
  step?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-secondary">
        {label}
      </span>
      <div className="flex items-center rounded-[8px] border border-border-subtle bg-surface px-3 py-2 focus-within:border-border-strong">
        <input
          type="number"
          inputMode="decimal"
          step={step}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="tnum w-full bg-transparent text-sm text-text-primary outline-none placeholder:text-text-tertiary"
        />
        {suffix && <span className="ml-2 text-[12px] text-text-tertiary">{suffix}</span>}
      </div>
    </label>
  );
}

export default function StakeCalculator() {
  const [prob, setProb] = useState("56.4");
  const [price, setPrice] = useState("138");
  const [bankroll, setBankroll] = useState("1000");
  const [kelly, setKelly] = useState("0.25");
  const [res, setRes] = useState<EVResponse | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    const p = parseFloat(prob) / 100;
    const ml = parseInt(price, 10);
    const bk = parseFloat(bankroll) || 0;
    const kf = parseFloat(kelly);
    if (!(p > 0 && p < 1) || !Number.isFinite(ml) || ml === 0 || !(kf >= 0 && kf <= 1)) {
      setRes(null);
      return;
    }
    let cancelled = false;
    postEv({ prob: p, american_price: ml, bankroll: bk, kelly_fraction: kf })
      .then((r) => !cancelled && (setRes(r), setErr(false)))
      .catch(() => !cancelled && setErr(true));
    return () => {
      cancelled = true;
    };
  }, [prob, price, bankroll, kelly]);

  const evTone = res && res.ev_per_unit >= 0 ? "text-pos" : "text-neg";

  return (
    <div className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border-subtle bg-border-subtle lg:grid-cols-[320px_1fr]">
      {/* Inputs */}
      <div className="flex flex-col gap-4 bg-surface px-5 py-5">
        <Field label="Model win probability" suffix="%" value={prob} onChange={setProb} step="0.1" />
        <Field label="American odds" value={price} onChange={setPrice} />
        <Field label="Bankroll" suffix="$" value={bankroll} onChange={setBankroll} step="50" />
        <Field label="Kelly fraction" value={kelly} onChange={setKelly} step="0.05" />
      </div>

      {/* Output */}
      <div className="bg-surface px-6 py-5">
        {err ? (
          <p className="text-sm text-text-secondary">Calculator offline. Check the serving layer.</p>
        ) : !res ? (
          <p className="text-sm text-text-tertiary">Enter a probability between 0 and 100, a non-zero line, and a Kelly fraction in [0, 1].</p>
        ) : (
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-3">
              <Out label="Implied prob" value={pct(res.implied_prob)} />
              <Out label="Edge" value={signedPct(res.edge)} tone={res.edge >= 0 ? "text-pos" : "text-neg"} />
              <Out label="EV / unit" value={signedPct(res.ev_per_unit)} tone={evTone} />
              <Out label="Decimal odds" value={res.decimal_odds.toFixed(2)} />
              <Out label="Full Kelly" value={pct(res.full_kelly)} />
              <Out label="Sized stake" value={pct(res.sized_kelly)} tone="text-accent" />
            </div>
            <div className="border-t border-border-subtle pt-4">
              <div className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-secondary">
                Recommended stake
              </div>
              <div className={`tnum mt-1 text-3xl font-semibold ${res.ev_per_unit >= 0 ? "text-text-primary" : "text-text-tertiary"}`}>
                ${res.recommended_stake.toFixed(2)}
              </div>
              {res.ev_per_unit < 0 && (
                <p className="mt-2 text-[12px] text-text-tertiary">
                  Negative EV. The model says pass. <span className="text-accent">∎</span>
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Out({ label, value, tone = "text-text-primary" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-secondary">{label}</span>
      <span className={`tnum text-xl font-semibold ${tone}`}>{value}</span>
    </div>
  );
}
