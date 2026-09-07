"use client";

import { useState } from "react";
import { Search, Filter, Download, FolderArchive } from "lucide-react";
import DashboardLayout from "@/components/layout/DashboardLayout";

export default function RecordsPage() {
  const [search, setSearch] = useState("");
  const records: any[] = []; // Real empty record list until grading occurs

  const filtered = records.filter((r) =>
    r.student?.toLowerCase().includes(search.toLowerCase()) ||
    r.unit?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-extrabold text-neutral-900 tracking-tight">Records</h1>
            <p className="text-xs text-neutral-500 font-medium mt-0.5">
              Historical graded assignments, candidate marks, and generated feedback reports.
            </p>
          </div>
        </div>

        {/* Search & Filter Bar */}
        <div className="bg-white rounded-2xl p-4 border border-neutral-100/80 shadow-sm flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-neutral-50 border border-neutral-200/80 flex-1 max-w-md">
            <Search className="w-4 h-4 text-neutral-400" />
            <input
              type="text"
              placeholder="Search candidate name or unit..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-transparent text-xs font-medium text-neutral-800 outline-none w-full placeholder:text-neutral-400"
            />
          </div>

          <button className="flex items-center gap-2 px-3.5 py-2 rounded-xl border border-neutral-200 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 transition">
            <Filter className="w-3.5 h-3.5" />
            <span>Filter</span>
          </button>
        </div>

        {/* Table Card */}
        <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm">
          {filtered.length === 0 ? (
            <div className="py-16 flex flex-col items-center justify-center text-center text-neutral-400">
              <FolderArchive className="w-10 h-10 stroke-[1.5] mb-2 text-neutral-300" />
              <p className="text-xs font-semibold text-neutral-600">No grading records found</p>
              <p className="text-[11px] text-neutral-400 mt-0.5 font-normal">
                Graded assignments and generated PDF feedback reports will be indexed and searchable here.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="text-neutral-400 font-semibold border-b border-neutral-100">
                    <th className="pb-3">Candidate</th>
                    <th className="pb-3">Unit</th>
                    <th className="pb-3">College</th>
                    <th className="pb-3">Grade</th>
                    <th className="pb-3">Verdict</th>
                    <th className="pb-3">Date</th>
                    <th className="pb-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-50">
                  {filtered.map((row) => (
                    <tr key={row.id} className="hover:bg-neutral-50/50 transition">
                      <td className="py-3.5 font-bold text-neutral-900">{row.student}</td>
                      <td className="py-3.5 text-neutral-600 font-medium">{row.unit}</td>
                      <td className="py-3.5 text-neutral-500 font-semibold">{row.college}</td>
                      <td className="py-3.5 font-semibold text-neutral-900">{row.grade}</td>
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
                      <td className="py-3.5 text-neutral-500 font-medium">{row.date}</td>
                      <td className="py-3.5 text-right">
                        <button className="p-1.5 rounded-lg text-neutral-500 hover:text-black hover:bg-neutral-100 transition">
                          <Download className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
