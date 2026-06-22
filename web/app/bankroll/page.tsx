import type { Metadata } from "next";
import StakeCalculator from "@/components/StakeCalculator";

export const metadata: Metadata = { title: "Bankroll" };

export default function Bankroll() {
  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="border-b border-border-subtle pb-5">
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          Bankroll &amp; Stake Sizing
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Fractional-Kelly sizing from a model probability and a price. Discipline over action.
        </p>
      </header>

      <div className="mt-8">
        <StakeCalculator />
      </div>

      <p className="mt-8 max-w-2xl text-[12px] leading-relaxed text-text-tertiary">
        For analysis only. Fractional Kelly trades growth for variance control; most disciplined
        bettors stake a quarter Kelly or less. Set limits, never chase, and treat any stake as
        money you can lose. <span className="text-accent">∎</span>
      </p>
    </div>
  );
}
