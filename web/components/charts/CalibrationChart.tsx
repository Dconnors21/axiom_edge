"use client";

import { motion } from "motion/react";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { LinePath, Line, Circle } from "@visx/shape";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows, GridColumns } from "@visx/grid";
import { ParentSize } from "@visx/responsive";
import type { CalibrationBucket } from "@/types/api";
import { chart, tickLabelProps, axisLabelProps } from "@/lib/chartTheme";

const M = { top: 12, right: 16, bottom: 40, left: 44 };

function Inner({
  width,
  data,
}: {
  width: number;
  data: CalibrationBucket[];
}) {
  const height = Math.max(220, Math.min(width * 0.7, 300));
  const iw = width - M.left - M.right;
  const ih = height - M.top - M.bottom;

  const x = scaleLinear({ domain: [0, 1], range: [0, iw] });
  const y = scaleLinear({ domain: [0, 1], range: [ih, 0] });
  const pts = [...data].sort((a, b) => a.predicted - b.predicted);
  const maxN = Math.max(...pts.map((p) => p.n), 1);

  return (
    <svg width={width} height={height}>
      <Group left={M.left} top={M.top}>
        <GridRows scale={y} width={iw} stroke={chart.grid} numTicks={4} />
        <GridColumns scale={x} height={ih} stroke={chart.grid} numTicks={4} />

        {/* Perfect-calibration diagonal */}
        <Line
          from={{ x: 0, y: ih }}
          to={{ x: iw, y: 0 }}
          stroke={chart.reference}
          strokeWidth={1}
          strokeDasharray="3,3"
        />

        {/* Reliability line (accent) drawn once on mount */}
        <motion.g
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.26, ease: [0.23, 1, 0.32, 1] }}
        >
          <LinePath
            data={pts}
            x={(d) => x(d.predicted)}
            y={(d) => y(d.actual)}
            stroke={chart.accent}
            strokeWidth={1.5}
          />
          {pts.map((d) => (
            <Circle
              key={d.bucket}
              cx={x(d.predicted)}
              cy={y(d.actual)}
              r={3 + 4 * (d.n / maxN)}
              fill={chart.accent}
              fillOpacity={0.9}
            />
          ))}
        </motion.g>

        <AxisBottom
          top={ih}
          scale={x}
          numTicks={5}
          stroke={chart.axis}
          tickStroke={chart.axis}
          tickFormat={(v) => `${Math.round(Number(v) * 100)}%`}
          tickLabelProps={tickLabelProps}
          label="Predicted"
          labelProps={{ ...axisLabelProps, dy: "2.4em" }}
        />
        <AxisLeft
          scale={y}
          numTicks={4}
          stroke={chart.axis}
          tickStroke={chart.axis}
          tickFormat={(v) => `${Math.round(Number(v) * 100)}%`}
          tickLabelProps={() => ({ ...tickLabelProps(), textAnchor: "end", dx: "-0.3em", dy: "0.3em" })}
          label="Actual"
          labelProps={{ ...axisLabelProps, dx: "-1.8em" }}
        />
      </Group>
    </svg>
  );
}

export default function CalibrationChart({ data }: { data: CalibrationBucket[] }) {
  return (
    <div className="h-[280px] w-full">
      <ParentSize>{({ width }) => (width > 0 ? <Inner width={width} data={data} /> : null)}</ParentSize>
    </div>
  );
}
