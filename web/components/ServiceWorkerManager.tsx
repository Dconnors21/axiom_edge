"use client";

import { useEffect, useState } from "react";

// Registers the service worker and surfaces an "update available" toast when a
// new version is waiting — no silent mid-session hot-swaps.
export default function ServiceWorkerManager() {
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);

  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;

    let refreshing = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });

    navigator.serviceWorker
      .register("/sw.js")
      .then((reg) => {
        if (reg.waiting) setWaiting(reg.waiting);
        reg.addEventListener("updatefound", () => {
          const next = reg.installing;
          next?.addEventListener("statechange", () => {
            if (next.state === "installed" && navigator.serviceWorker.controller) {
              setWaiting(next);
            }
          });
        });
      })
      .catch(() => {});
  }, []);

  if (!waiting) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 flex justify-center p-4">
      <div className="flex items-center gap-4 rounded-md border border-border-strong bg-surface-overlay px-4 py-2.5 shadow-lg">
        <span className="text-[13px] text-text-secondary">New version available.</span>
        <button
          onClick={() => waiting.postMessage({ type: "SKIP_WAITING" })}
          className="rounded-[8px] bg-accent px-3 py-1 text-[13px] font-medium text-bg transition-transform duration-[var(--dur-micro)] active:scale-[0.97]"
        >
          Refresh
        </button>
      </div>
    </div>
  );
}
