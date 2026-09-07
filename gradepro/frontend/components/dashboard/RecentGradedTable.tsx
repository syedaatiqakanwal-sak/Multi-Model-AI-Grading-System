"use client";

import { FileSpreadsheet } from "lucide-react";

interface GradedRow {
  name: string;
  avatar: string;
  unit: string;
  grade: string;
  result: "Pass" | "Refer";
  date: string;
}

interface RecentGradedTableProps {
  grades?: GradedRow[];
}

export default function RecentGradedTable({ grades = [] }: RecentGradedTableProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.04)]">
      {/* Table Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-bold text-neutral-900">Recent Graded</h3>
        {grades.length > 0 && (
          <button className="px-3 py-1.5 rounded-lg border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 transition">
            View All
          </button>
        )}
      </div>

      {/* Table Content */}
      {grades.length === 0 ? (
        <div className="py-12 flex flex-col items-center justify-center text-center text-neutral-400">
          <FileSpreadsheet className="w-9 h-9 stroke-[1.5] mb-2 text-neutral-300" />
          <p className="text-xs font-semibold text-neutral-600">No assignments graded yet</p>
          <p className="text-[11px] text-neutral-400 mt-0.5 font-normal">
            New submissions and AI assessment reports will appear here automatically.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-neutral-400 font-semibold border-b border-neutral-100">
                <th className="pb-3 font-semibold">Student / Candidate</th>
                <th className="pb-3 font-semibold">Unit</th>
                <th className="pb-3 font-semibold">Grade</th>
                <th className="pb-3 font-semibold">Result</th>
                <th className="pb-3 font-semibold text-right">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-50">
              {grades.map((row, idx) => (
                <tr key={idx} className="hover:bg-neutral-50/50 transition">
                  <td className="py-3.5 flex items-center gap-2.5">
                    <div className="w-7 h-7 rounded-full bg-neutral-900 text-white flex items-center justify-center font-bold text-[11px]">
                      {row.avatar}
                    </div>
                    <span className="font-semibold text-neutral-900">{row.name}</span>
                  </td>
                  <td className="py-3.5 text-neutral-600 font-medium">{row.unit}</td>
                  <td className="py-3.5 text-neutral-900 font-semibold">{row.grade}</td>
                  <td className="py-3.5">
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-[11px] font-semibold ${
                        row.result === "Pass"
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200/60"
                          : "bg-rose-50 text-rose-700 border border-rose-200/60"
                      }`}
                    >
                      {row.result}
                    </span>
                  </td>
                  <td className="py-3.5 text-neutral-500 font-medium text-right">{row.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
