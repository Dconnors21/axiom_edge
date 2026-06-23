"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowClockwise } from "@phosphor-icons/react";

const THRESHOLD = 70;
const MAX = 90;

// Pull down at the top of the scroll area to refresh the live data (router
// refresh re-runs the server components). Honors reduced-motion: the gesture
// still refreshes, but the animated indicator is suppressed.
export default function PullToRefresh() {
  const router = useRouter();
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const pullRef = useRef(0);
  const startY = useRef<number | null>(null);

  useEffect(() => {
    const main = document.querySelector("main");
    if (!main) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const set = (v: number) => {
      pullRef.current = v;
      setPull(reduce ? 0 : v);
    };
    const onStart = (e: TouchEvent) => {
      if (main.scrollTop <= 0) startY.current = e.touches[0].clientY;
    };
    const onMove = (e: TouchEvent) => {
      if (startY.current == null) return;
      const d = e.touches[0].clientY - startY.current;
      if (d > 0 && main.scrollTop <= 0) set(Math.min(d * 0.5, MAX)); // boundary damping
    };
    const onEnd = () => {
      if (pullRef.current > THRESHOLD) {
        setRefreshing(true);
        setPull(reduce ? 0 : THRESHOLD);
        router.refresh();
        setTimeout(() => {
          setRefreshing(false);
          set(0);
        }, 600);
      } else {
        set(0);
      }
      startY.current = null;
    };
    main.addEventListener("touchstart", onStart, { passive: true });
    main.addEventListener("touchmove", onMove, { passive: true });
    main.addEventListener("touchend", onEnd);
    return () => {
      main.removeEventListener("touchstart", onStart);
      main.removeEventListener("touchmove", onMove);
      main.removeEventListener("touchend", onEnd);
    };
  }, [router]);

  if (pull <= 0 && !refreshing) return null;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 top-0 z-20 flex justify-center md:hidden"
      style={{ transform: `translateY(${Math.min(pull, MAX)}px)`, opacity: Math.min(pull / THRESHOLD, 1) }}
    >
      <div className="mt-2 rounded-full border border-border-subtle bg-surface-overlay p-2">
        <ArrowClockwise
          className={`text-[16px] text-accent ${refreshing ? "animate-spin" : ""}`}
          style={{ transform: refreshing ? undefined : `rotate(${pull * 3}deg)` }}
        />
      </div>
    </div>
  );
}
