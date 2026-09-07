"use client";

import {
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { ChevronDown, LineChart as ChartIcon } from "lucide-react";

interface DataPoint {
  day: string;
  pass: number;
  refer: number;
}

interface PassReferLineChartProps {
  data?: DataPoint[];
}

export default function PassReferLineChart({ data = [] }: PassReferLineChartProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.04)]">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-base font-bold text-neutral-900">Pass vs Refer Overview</h3>
          <div className="flex items-center gap-4 mt-2">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-700">
              <span className="w-2.5 h-2.5 rounded-full bg-brand-purple"></span>
              <span>Pass</span>
            </div>
            <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-700">
              <span className="w-2.5 h-2.5 rounded-full bg-black"></span>
              <span>Refer</span>
            </div>
          </div>
        </div>

        <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 transition">
          <span>This Week</span>
          <ChevronDown className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Chart or Empty State */}
      {data.length === 0 ? (
        <div className="h-64 w-full flex flex-col items-center justify-center text-center text-neutral-400">
          <ChartIcon className="w-9 h-9 stroke-[1.5] mb-2 text-neutral-300" />
          <p className="text-xs font-semibold text-neutral-600">No grading activity in this period</p>
          <p className="text-[11px] text-neutral-400 mt-0.5 font-normal">
            Weekly trends will populate as assessors complete grading sessions.
          </p>
        </div>
      ) : (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="passGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.35} />
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.05} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#F0F0F0" />
              <XAxis
                dataKey="day"
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 12, fill: "#737373" }}
                dy={10}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fontSize: 12, fill: "#737373" }}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#000",
                  borderRadius: "8px",
                  color: "#fff",
                  border: "none",
                  fontSize: "12px",
                }}
              />
              <Area
                type="monotone"
                dataKey="pass"
                stroke="#8b5cf6"
                strokeWidth={3}
                fillOpacity={1}
                fill="url(#passGradient)"
                dot={{ r: 4, fill: "#8b5cf6", stroke: "#000000", strokeWidth: 1.5 }}
              />
              <Line
                type="monotone"
                dataKey="refer"
                stroke="#000000"
                strokeWidth={2.5}
                dot={{ r: 4, fill: "#000000", stroke: "#fff", strokeWidth: 1.5 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
