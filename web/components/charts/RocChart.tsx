"use client";

import { motion } from "motion/react";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { LinePath, Line } from "@visx/shape";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows, GridColumns } from "@visx/grid";
import { ParentSize } from "@visx/responsive";
import type { RocPoint } from "@/types/api";
import { chart, tickLabelProps, axisLabelProps } from "@/lib/chartTheme";

const M = { top: 12, right: 16, bottom: 40, left: 44 };

function Inner({ width, data }: { width: number; data: RocPoint[] }) {
  const height = Math.max(220, Math.min(width * 0.7, 300));
  const iw = width - M.left - M.right;
  const ih = height - M.top - M.bottom;

  const x = scaleLinear({ domain: [0, 1], range: [0, iw] });
  const y = scaleLinear({ domain: [0, 1], range: [ih, 0] });

  return (
    <svg width={width} height={height}>
      <Group left={M.left} top={M.top}>
        <GridRows scale={y} width={iw} stroke={chart.grid} numTicks={4} />
        <GridColumns scale={x} height={ih} stroke={chart.grid} numTicks={4} />

        {/* Random-classifier diagonal */}
        <Line
          from={{ x: 0, y: ih }}
          to={{ x: iw, y: 0 }}
          stroke={chart.reference}
          strokeWidth={1}
          strokeDasharray="3,3"
        />

        <motion.g
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.26, ease: [0.23, 1, 0.32, 1] }}
        >
          <LinePath
            data={data}
            x={(d) => x(d.fpr)}
            y={(d) => y(d.tpr)}
            stroke={chart.accent}
            strokeWidth={1.5}
          />
        </motion.g>

        <AxisBottom
          top={ih}
          scale={x}
          numTicks={5}
          stroke={chart.axis}
          tickStroke={chart.axis}
          tickFormat={(v) => `${Math.round(Number(v) * 100)}%`}
          tickLabelProps={tickLabelProps}
          label="False positive rate"
          labelProps={{ ...axisLabelProps, dy: "2.4em" }}
        />
        <AxisLeft
          scale={y}
          numTicks={4}
          stroke={chart.axis}
          tickStroke={chart.axis}
          tickFormat={(v) => `${Math.round(Number(v) * 100)}%`}
          tickLabelProps={() => ({ ...tickLabelProps(), textAnchor: "end", dx: "-0.3em", dy: "0.3em" })}
          label="True positive rate"
          labelProps={{ ...axisLabelProps, dx: "-1.8em" }}
        />
      </Group>
    </svg>
  );
}

export default function RocChart({ data }: { data: RocPoint[] }) {
  return (
    <div className="h-[280px] w-full">
      <ParentSize>{({ width }) => (width > 0 ? <Inner width={width} data={data} /> : null)}</ParentSize>
    </div>
  );
}
