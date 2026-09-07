"use client";

import {
  ClipboardList,
  CheckCircle2,
  XCircle,
  Percent,
  Calendar,
  Bell,
  ChevronDown,
} from "lucide-react";
import DashboardLayout from "@/components/layout/DashboardLayout";
import StatCard from "@/components/dashboard/StatCard";
import PassReferLineChart from "@/components/dashboard/PassReferLineChart";
import PassReferDonut from "@/components/dashboard/PassReferDonut";
import RecentGradedTable from "@/components/dashboard/RecentGradedTable";
import MostGradedUnitsTable from "@/components/dashboard/MostGradedUnitsTable";
import { useAuthStore } from "@/lib/auth";

export default function DashboardPage() {
  const user = useAuthStore((s) => s.user);

  // Clean dynamic state — ready for backend sync
  const stats = {
    totalGraded: 0,
    passCount: 0,
    referCount: 0,
    passRate: "0.0%",
  };

  const chartData: any[] = [];
  const recentGrades: any[] = [];
  const mostGradedUnits: any[] = [];

  const todayStr = new Date().toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });

  return (
    <DashboardLayout>
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-extrabold text-neutral-900 tracking-tight">
            Dashboard
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Welcome back, {user?.name || "Assessor"}! Here's what's happening today.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Date Picker Button */}
          <button className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white border border-neutral-200/90 text-xs font-semibold text-neutral-800 shadow-[0_2px_4px_rgba(0,0,0,0.02)] hover:bg-neutral-50 transition">
            <Calendar className="w-3.5 h-3.5 text-neutral-500" />
            <span>{todayStr}</span>
            <ChevronDown className="w-3.5 h-3.5 text-neutral-400" />
          </button>

          {/* Notifications Bell */}
          <button className="relative w-9 h-9 rounded-xl bg-white border border-neutral-200/90 flex items-center justify-center text-neutral-700 shadow-[0_2px_4px_rgba(0,0,0,0.02)] hover:bg-neutral-50 transition">
            <Bell className="w-4 h-4" />
          </button>

          {/* Profile Circle */}
          <div className="w-9 h-9 rounded-full bg-neutral-900 text-white flex items-center justify-center font-bold text-xs shadow-sm">
            {user?.name?.slice(0, 2).toUpperCase() || "AS"}
          </div>
        </div>
      </div>

      {/* 4 Top Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatCard
          title="Total Graded"
          value={stats.totalGraded.toString()}
          change="0.0%"
          isPositive={true}
          icon={ClipboardList}
        />
        <StatCard
          title="Pass"
          value={stats.passCount.toString()}
          change="0.0%"
          isPositive={true}
          icon={CheckCircle2}
        />
        <StatCard
          title="Refer"
          value={stats.referCount.toString()}
          change="0.0%"
          isPositive={false}
          icon={XCircle}
        />
        <StatCard
          title="Pass Rate"
          value={stats.passRate}
          change="0.0%"
          isPositive={true}
          icon={Percent}
        />
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <PassReferLineChart data={chartData} />
        </div>
        <div className="lg:col-span-1">
          <PassReferDonut passCount={stats.passCount} referCount={stats.referCount} />
        </div>
      </div>

      {/* Tables Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <RecentGradedTable grades={recentGrades} />
        <MostGradedUnitsTable units={mostGradedUnits} />
      </div>
    </DashboardLayout>
  );
}
