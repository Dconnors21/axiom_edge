import type { Metadata } from "next";

export const metadata: Metadata = { title: "Offline" };

// Shown by the service worker when a page is requested with no network.
// Deliberately shows NO odds — perishable data is never served stale.
export default function Offline() {
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col items-start justify-center px-8">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold tracking-tight text-text-primary">AXIOM</span>
        <span className="text-2xl leading-none text-accent">∎</span>
      </div>
      <h1 className="mt-4 text-lg font-semibold text-text-primary">You&apos;re offline.</h1>
      <p className="mt-2 text-sm text-text-secondary">
        Odds and edges are live, so nothing is shown rather than something stale. Reconnect to
        load tonight&apos;s slate.
      </p>
      <a
        href="/"
        className="mt-6 rounded-[8px] border border-border-strong bg-surface-elevated px-4 py-2 text-sm font-medium text-text-primary transition-transform duration-[var(--dur-micro)] [@media(hover:hover)]:hover:bg-surface-overlay active:scale-[0.97]"
      >
        Retry
      </a>
    </div>
  );
}
