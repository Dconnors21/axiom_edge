type Tone = "primary" | "secondary" | "accent" | "pos" | "neg";

const TONE: Record<Tone, string> = {
  primary: "text-text-primary",
  secondary: "text-text-secondary",
  accent: "text-accent",
  pos: "text-pos",
  neg: "text-neg",
};

export default function StatBlock({
  label,
  value,
  tone = "primary",
}: {
  label: string;
  value: string;
  tone?: Tone;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-secondary">
        {label}
      </span>
      <span className={`tnum text-xl font-semibold ${TONE[tone]}`}>{value}</span>
    </div>
  );
}
