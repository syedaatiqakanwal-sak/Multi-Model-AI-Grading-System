"use client";

import { Layers } from "lucide-react";

interface UnitRow {
  unit: string;
  total: number;
  passRate: number;
}

interface MostGradedUnitsTableProps {
  units?: UnitRow[];
}

export default function MostGradedUnitsTable({ units = [] }: MostGradedUnitsTableProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.04)]">
      {/* Table Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-bold text-neutral-900">Most Graded Units</h3>
        {units.length > 0 && (
          <button className="px-3 py-1.5 rounded-lg border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 transition">
            View All
          </button>
        )}
      </div>

      {/* Table Content */}
      {units.length === 0 ? (
        <div className="py-12 flex flex-col items-center justify-center text-center text-neutral-400">
          <Layers className="w-9 h-9 stroke-[1.5] mb-2 text-neutral-300" />
          <p className="text-xs font-semibold text-neutral-600">No unit activity recorded</p>
          <p className="text-[11px] text-neutral-400 mt-0.5 font-normal">
            Unit breakdown and aggregate pass rates will be calculated as assessments are graded.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-neutral-400 font-semibold border-b border-neutral-100">
                <th className="pb-3 font-semibold">Unit</th>
                <th className="pb-3 font-semibold text-center">Total Graded</th>
                <th className="pb-3 font-semibold text-right">Pass Rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-50">
              {units.map((row, idx) => (
                <tr key={idx} className="hover:bg-neutral-50/50 transition">
                  <td className="py-3.5 font-medium text-neutral-800">{row.unit}</td>
                  <td className="py-3.5 text-neutral-900 font-bold text-center">{row.total}</td>
                  <td className="py-3.5 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <span className="font-semibold text-neutral-900 w-8">{row.passRate}%</span>
                      <div className="w-24 h-2 rounded-full bg-neutral-100 overflow-hidden">
                        <div
                          className="h-full bg-brand-purple rounded-full"
                          style={{ width: `${row.passRate}%` }}
                        ></div>
                      </div>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
