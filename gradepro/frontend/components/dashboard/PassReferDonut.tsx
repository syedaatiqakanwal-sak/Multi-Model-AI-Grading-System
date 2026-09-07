"use client";

import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import { PieChart as PieIcon } from "lucide-react";

interface PassReferDonutProps {
  passCount?: number;
  referCount?: number;
}

export default function PassReferDonut({ passCount = 0, referCount = 0 }: PassReferDonutProps) {
  const total = passCount + referCount;
  const passPct = total > 0 ? ((passCount / total) * 100).toFixed(1) : "0.0";
  const referPct = total > 0 ? ((referCount / total) * 100).toFixed(1) : "0.0";

  const data = total > 0
    ? [
        { name: "Pass", value: passCount, color: "#8b5cf6" },
        { name: "Refer", value: referCount, color: "#111111" },
      ]
    : [{ name: "None", value: 1, color: "#E5E5E5" }];

  return (
    <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.04)] flex flex-col justify-between">
      <h3 className="text-base font-bold text-neutral-900 mb-2">
        Pass vs Refer Distribution
      </h3>

      {total === 0 ? (
        <div className="py-12 flex flex-col items-center justify-center text-center text-neutral-400">
          <PieIcon className="w-9 h-9 stroke-[1.5] mb-2 text-neutral-300" />
          <p className="text-xs font-semibold text-neutral-600">No distribution data</p>
          <p className="text-[11px] text-neutral-400 mt-0.5 font-normal">
            Ratio of passed vs referred assessments.
          </p>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-4 my-auto">
          {/* Donut Chart with Center Text */}
          <div className="relative w-44 h-44 shrink-0 mx-auto">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  innerRadius={52}
                  outerRadius={76}
                  paddingAngle={0}
                  dataKey="value"
                  startAngle={90}
                  endAngle={-270}
                >
                  {data.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} stroke="none" />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
              <span className="text-xl font-extrabold text-neutral-900 leading-tight">
                {total.toLocaleString()}
              </span>
              <span className="text-[11px] text-neutral-400 font-medium">Total</span>
            </div>
          </div>

          {/* Legend */}
          <div className="space-y-4 shrink-0 pr-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-brand-purple"></span>
                <span className="text-sm font-bold text-neutral-900">Pass</span>
              </div>
              <p className="text-xs text-neutral-500 font-medium pl-5 mt-0.5">
                {passCount.toLocaleString()} ({passPct}%)
              </p>
            </div>

            <div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-neutral-950"></span>
                <span className="text-sm font-bold text-neutral-900">Refer</span>
              </div>
              <p className="text-xs text-neutral-500 font-medium pl-5 mt-0.5">
                {referCount.toLocaleString()} ({referPct}%)
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
