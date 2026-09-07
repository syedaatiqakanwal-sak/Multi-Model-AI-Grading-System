import { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: string;
  change: string;
  isPositive: boolean;
  icon: LucideIcon;
  iconBgColor?: string;
}

export default function StatCard({
  title,
  value,
  change,
  isPositive,
  icon: Icon,
}: StatCardProps) {
  return (
    <div className="bg-white rounded-2xl p-6 border border-neutral-100/80 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.04)] flex items-start gap-4">
      <div className="w-12 h-12 rounded-xl bg-brand-white border border-brand-purple flex items-center justify-center text-brand-black shrink-0">
        <Icon className="w-6 h-6 stroke-[2]" />
      </div>

      <div className="flex-1">
        <p className="text-xs font-semibold text-neutral-500 tracking-wide uppercase">
          {title}
        </p>
        <h3 className="text-2xl font-extrabold text-neutral-900 mt-1 tracking-tight">
          {value}
        </h3>
        <p
          className={`text-xs font-semibold mt-2 flex items-center gap-1 ${
            isPositive ? "text-amber-700" : "text-neutral-700"
          }`}
        >
          <span>{isPositive ? "↑" : "↓"}</span>
          <span>{change}</span>
          <span className="text-neutral-400 font-normal">from last week</span>
        </p>
      </div>
    </div>
  );
}
