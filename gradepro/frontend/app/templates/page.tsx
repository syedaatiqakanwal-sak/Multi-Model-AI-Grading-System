"use client";

import { useState } from "react";
import { Plus, FileText, Check, LayoutTemplate } from "lucide-react";
import DashboardLayout from "@/components/layout/DashboardLayout";

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<any[]>([
    {
      id: "hsc301-ukpda",
      unit: "HSC301",
      name: "An Introduction to Health and Social Care",
      college: "UKPDA",
      version: 1,
      active: true,
    },
    {
      id: "hsc301-ilc",
      unit: "HSC301",
      name: "An Introduction to Health and Social Care",
      college: "ILC",
      version: 1,
      active: true,
    },
  ]);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-extrabold text-neutral-900 tracking-tight">Feedback Templates</h1>
            <p className="text-xs text-neutral-500 font-medium mt-0.5">
              Manage and hot-swap per-unit DOCX feedback templates for ILC and UKPDA.
            </p>
          </div>

          <button className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#8b5cf6] text-black font-bold text-xs shadow-sm hover:bg-[#8b5cf6] transition">
            <Plus className="w-4 h-4" />
            <span>Upload New Template</span>
          </button>
        </div>

        {templates.length === 0 ? (
          <div className="bg-white rounded-2xl p-16 border border-neutral-100/80 shadow-sm flex flex-col items-center justify-center text-center text-neutral-400">
            <LayoutTemplate className="w-10 h-10 stroke-[1.5] mb-2 text-neutral-300" />
            <p className="text-xs font-semibold text-neutral-600">No custom templates uploaded yet</p>
            <p className="text-[11px] text-neutral-400 mt-0.5 font-normal">
              Click &quot;Upload New Template&quot; to register a DOCX feedback template for a unit.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {templates.map((t) => (
              <div key={t.id} className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-sm flex flex-col justify-between space-y-4">
                <div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-neutral-600 bg-neutral-100 px-2 py-0.5 rounded">
                      {t.college}
                    </span>
                    <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded flex items-center gap-1">
                      <Check className="w-3 h-3" /> Active v{t.version}
                    </span>
                  </div>
                  <h3 className="text-base font-bold text-neutral-900 mt-3">{t.unit}</h3>
                  <p className="text-xs text-neutral-600 font-medium">{t.name}</p>
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-neutral-100 text-xs">
                  <button className="font-semibold text-neutral-700 hover:text-black">Preview DOCX</button>
                  <button className="font-bold text-[#8b5cf6] hover:text-[#8b5cf6]">Replace File</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
