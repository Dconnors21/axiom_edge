"use client";

import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { LinePath, Line, Circle } from "@visx/shape";
import { curveMonotoneX } from "@visx/curve";
import { chart } from "@/lib/chartTheme";

// Minimal trend line: no axes, no grid. Reads at a glance inside a stat row.
export default function Sparkline({
  data,
  width = 120,
  height = 32,
  tone,
}: {
  data: number[];
  width?: number;
  height?: number;
  tone?: string;
}) {
  if (data.length < 2) {
    return <div style={{ width, height }} aria-hidden />;
  }
  const pad = 3;
  const x = scaleLinear({ domain: [0, data.length - 1], range: [pad, width - pad] });
  const lo = Math.min(...data);
  const hi = Math.max(...data);
  const y = scaleLinear({ domain: [lo, hi === lo ? lo + 1 : hi], range: [height - pad, pad] });
  const pts = data.map((v, i) => ({ i, v }));
  const last = pts[pts.length - 1];
  const color = tone ?? chart.accent;
  const mean = data.reduce((a, b) => a + b, 0) / data.length;

  return (
    <svg width={width} height={height} role="img" aria-label="Last 10 games trend">
      <Group>
        {/* average baseline */}
        <Line from={{ x: pad, y: y(mean) }} to={{ x: width - pad, y: y(mean) }} stroke={chart.grid} strokeWidth={1} />
        <LinePath data={pts} x={(d) => x(d.i)} y={(d) => y(d.v)} stroke={color} strokeWidth={1.5} curve={curveMonotoneX} />
        <Circle cx={x(last.i)} cy={y(last.v)} r={2.5} fill={color} />
      </Group>
    </svg>
  );
}
