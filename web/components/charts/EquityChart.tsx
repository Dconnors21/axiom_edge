"use client";

import { motion } from "motion/react";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { LinePath, Line, AreaClosed } from "@visx/shape";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { ParentSize } from "@visx/responsive";
import { curveMonotoneX } from "@visx/curve";
import type { EquityPoint } from "@/types/api";
import { chart, tickLabelProps, axisLabelProps } from "@/lib/chartTheme";

const M = { top: 12, right: 16, bottom: 38, left: 48 };

type Pt = { i: number; v: number };

function Inner({ width, data }: { width: number; data: EquityPoint[] }) {
  const height = 260;
  const iw = width - M.left - M.right;
  const ih = height - M.top - M.bottom;

  const pts: Pt[] = data.map((d, i) => ({ i, v: d.cumulative }));
  const vals = pts.map((p) => p.v).concat(0);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const pad = (max - min || 1) * 0.1;

  const x = scaleLinear({ domain: [0, Math.max(pts.length - 1, 1)], range: [0, iw] });
  const y = scaleLinear({ domain: [min - pad, max + pad], range: [ih, 0] });
  const ending = pts.length ? pts[pts.length - 1].v : 0;
  const stroke = ending >= 0 ? chart.pos : chart.neg;

  return (
    <svg width={width} height={height}>
      <Group left={M.left} top={M.top}>
        <GridRows scale={y} width={iw} stroke={chart.grid} numTicks={4} />
        {/* Break-even baseline */}
        <Line from={{ x: 0, y: y(0) }} to={{ x: iw, y: y(0) }} stroke={chart.reference} strokeWidth={1} strokeDasharray="3,3" />

        <motion.g
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.26, ease: [0.23, 1, 0.32, 1] }}
        >
          <AreaClosed
            data={pts}
            x={(d) => x(d.i)}
            y={(d) => y(d.v)}
            yScale={y}
            curve={curveMonotoneX}
            fill={stroke}
            fillOpacity={0.08}
          />
          <LinePath
            data={pts}
            x={(d) => x(d.i)}
            y={(d) => y(d.v)}
            stroke={stroke}
            strokeWidth={1.5}
            curve={curveMonotoneX}
          />
        </motion.g>

        <AxisBottom
          top={ih}
          scale={x}
          numTicks={5}
          stroke={chart.axis}
          tickStroke={chart.axis}
          tickFormat={(v) => `${Math.round(Number(v))}`}
          tickLabelProps={tickLabelProps}
          label="Bet number"
          labelProps={{ ...axisLabelProps, dy: "2.2em" }}
        />
        <AxisLeft
          scale={y}
          numTicks={4}
          stroke={chart.axis}
          tickStroke={chart.axis}
          tickFormat={(v) => `${Number(v) >= 0 ? "+" : ""}${Number(v).toFixed(2)}u`}
          tickLabelProps={() => ({ ...tickLabelProps(), textAnchor: "end", dx: "-0.3em", dy: "0.3em" })}
        />
      </Group>
    </svg>
  );
}

export default function EquityChart({ data }: { data: EquityPoint[] }) {
  return (
    <div className="h-[260px] w-full">
      <ParentSize>{({ width }) => (width > 0 ? <Inner width={width} data={data} /> : null)}</ParentSize>
    </div>
  );
}
