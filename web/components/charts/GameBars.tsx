"use client";

import { ParentSize } from "@visx/responsive";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear } from "@visx/scale";
import { Bar, Line } from "@visx/shape";
import { Text } from "@visx/text";
import { chart } from "@/lib/chartTheme";

type Datum = { label: string; value: number };

function Chart({
  data,
  avg,
  width,
  height,
}: {
  data: Datum[];
  avg: number;
  width: number;
  height: number;
}) {
  const m = { top: 14, right: 8, bottom: 22, left: 8 };
  const iw = width - m.left - m.right;
  const ih = height - m.top - m.bottom;
  const max = Math.max(avg, ...data.map((d) => d.value), 1) * 1.15;

  const x = scaleBand({
    domain: data.map((_, i) => String(i)),
    range: [0, iw],
    padding: 0.3,
  });
  const y = scaleLinear({ domain: [0, max], range: [ih, 0] });
  const ay = y(avg);

  return (
    <svg width={width} height={height}>
      <Group left={m.left} top={m.top}>
        {data.map((d, i) => {
          const bx = x(String(i)) ?? 0;
          const bh = ih - y(d.value);
          const above = d.value >= avg;
          return (
            <g key={i}>
              <Bar
                x={bx}
                y={y(d.value)}
                width={x.bandwidth()}
                height={Math.max(0, bh)}
                rx={2}
                fill={above ? chart.accent : chart.series}
                opacity={above ? 1 : 0.45}
              />
              <Text
                x={bx + x.bandwidth() / 2}
                y={y(d.value) - 4}
                fontSize={9}
                textAnchor="middle"
                fill={chart.axis}
                fontFamily={chart.fontMono}
              >
                {d.value % 1 === 0 ? String(d.value) : d.value.toFixed(1)}
              </Text>
              <Text
                x={bx + x.bandwidth() / 2}
                y={ih + 14}
                fontSize={9}
                textAnchor="middle"
                fill={chart.axis}
                fontFamily={chart.fontMono}
              >
                {d.label}
              </Text>
            </g>
          );
        })}
        {/* average reference line */}
        <Line
          from={{ x: 0, y: ay }}
          to={{ x: iw, y: ay }}
          stroke={chart.reference}
          strokeWidth={1}
          strokeDasharray="3,3"
        />
        <Text x={iw} y={ay - 4} fontSize={9} textAnchor="end" fill={chart.axis} fontFamily={chart.fontMono}>
          {`avg ${avg.toFixed(1)}`}
        </Text>
      </Group>
    </svg>
  );
}

export default function GameBars({ data, avg, height = 168 }: { data: Datum[]; avg: number; height?: number }) {
  return (
    <div style={{ width: "100%", height }}>
      <ParentSize>{({ width }) => (width > 0 ? <Chart data={data} avg={avg} width={width} height={height} /> : null)}</ParentSize>
    </div>
  );
}
