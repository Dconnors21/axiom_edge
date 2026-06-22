function Bar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-elevated ${className}`} />;
}

export default function Loading() {
  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <div className="flex items-end justify-between border-b border-border-subtle pb-5">
        <div className="flex flex-col gap-2">
          <Bar className="h-5 w-28" />
          <Bar className="h-4 w-40" />
        </div>
        <Bar className="h-6 w-10" />
      </div>

      <div className="mt-8 flex flex-col gap-10">
        {/* AXIOM read */}
        <div className="rounded-md border border-border-subtle bg-surface px-6 py-6">
          <Bar className="h-3 w-48" />
          <Bar className="mt-4 h-7 w-56" />
          <Bar className="mt-3 h-4 w-72" />
          <div className="mt-6 grid grid-cols-4 gap-6">
            {Array.from({ length: 4 }).map((_, i) => (
              <Bar key={i} className="h-10" />
            ))}
          </div>
        </div>

        {/* edges */}
        <div className="overflow-hidden rounded-md border border-border-subtle">
          {Array.from({ length: 5 }).map((_, i) => (
            <div
              key={i}
              className={`bg-surface px-5 py-4 ${i > 0 ? "border-t border-border-subtle" : ""}`}
            >
              <Bar className="h-4 w-full" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
