import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { League } from "@/types/api";
import { getProps } from "@/lib/api";
import { slateDateLong } from "@/lib/format";
import PropsBoard from "@/components/PropsBoard";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "MLB Player Props" };

// Props live only on MLB in the current IA.
export default async function PropsPage({ params }: { params: Promise<{ league: string }> }) {
  const { league } = await params;
  if (league !== "mlb") notFound();

  const data = await getProps(league as League);

  return (
    <div className="mx-auto max-w-[1100px] px-8 py-10">
      <header className="flex items-end justify-between border-b border-border-subtle pb-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-text-primary">
            MLB Player Props
          </h1>
          <p className="mt-1 text-sm text-text-secondary">{slateDateLong(data.slate_date)}</p>
        </div>
        <div className="flex flex-col items-end gap-0.5">
          <span className="text-[10px] uppercase tracking-[0.06em] text-text-secondary">
            Value props
          </span>
          <span className="tnum text-lg font-semibold text-accent">{data.value_count}</span>
        </div>
      </header>

      {data.value_count === 0 ? (
        <div className="mt-10 rounded-md border border-border-subtle bg-surface px-6 py-10 text-center">
          <p className="text-sm text-text-secondary">No value props on the board.</p>
          <p className="mt-1 text-[13px] text-text-tertiary">
            Strikeouts, hits, and total bases are scanned each slate.{" "}
            <span className="text-accent">∎</span>
          </p>
        </div>
      ) : (
        <div className="mt-8">
          <PropsBoard props={data.props} />
        </div>
      )}
    </div>
  );
}
