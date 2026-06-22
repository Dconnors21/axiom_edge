"use client";

export default function Error({ reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col items-start px-8 py-16">
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-text-tertiary">
        Data unavailable
      </div>
      <h1 className="mt-3 text-xl font-semibold tracking-tight text-text-primary">
        Can&apos;t reach the model right now.
      </h1>
      <p className="mt-2 max-w-md text-sm text-text-secondary">
        The serving layer didn&apos;t respond. Odds and edges are live, so nothing is
        shown rather than something stale. <span className="text-accent">∎</span>
      </p>
      <button
        onClick={reset}
        className="mt-6 rounded-[8px] border border-border-strong bg-surface-elevated px-4 py-2 text-sm font-medium text-text-primary transition-transform duration-[var(--dur-micro)] [@media(hover:hover)]:hover:bg-surface-overlay active:scale-[0.97]"
      >
        Retry
      </button>
    </div>
  );
}
