"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Zap,
  MessageSquare,
  Folder,
  Settings,
  User,
  ClipboardCheck,
  ChevronDown,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";

const navItems = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Grade Now", href: "/grade", icon: Zap },
  { label: "Feedback Templates", href: "/templates", icon: MessageSquare },
  { label: "Record", href: "/records", icon: Folder },
  { label: "Setting", href: "/settings", icon: Settings },
  { label: "Profile", href: "/profile", icon: User },
];

export default function Sidebar() {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);

  return (
    <aside className="w-64 bg-brand-black text-brand-white flex flex-col justify-between h-screen sticky top-0 shrink-0 select-none">
      {/* Brand Header */}
      <div>
        <div className="p-6 pb-8">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-brand-purple flex items-center justify-center text-brand-black">
              <ClipboardCheck className="w-6 h-6 stroke-[2.5]" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-1">
                Grade<span className="text-brand-purple">Pro</span>
              </h1>
              <p className="text-[11px] text-neutral-400 font-medium tracking-tight">
                Smart Grading. Clear Results.
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="px-4 space-y-1.5">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3.5 px-4 py-3 rounded-xl font-medium text-sm transition-all ${
                  isActive
                    ? "bg-brand-purple text-brand-black font-semibold shadow-sm"
                    : "text-neutral-300 hover:text-white hover:bg-neutral-900/80"
                }`}
              >
                <Icon className={`w-5 h-5 ${isActive ? "text-black stroke-[2.5]" : "text-neutral-400"}`} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* User Footer Profile */}
      <div className="p-4 border-t border-neutral-800/60">
        <div className="flex items-center justify-between p-2 rounded-xl hover:bg-neutral-900/60 transition cursor-pointer">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-gradient-to-tr from-amber-400 to-yellow-200 border border-yellow-300 flex items-center justify-center text-black font-bold text-sm shadow-sm">
              SJ
            </div>
            <div className="text-left">
              <p className="text-sm font-semibold text-white leading-tight">
                {user?.name || "Sarah Johnson"}
              </p>
              <p className="text-xs text-neutral-400 font-medium">Administrator</p>
            </div>
          </div>
          <ChevronDown className="w-4 h-4 text-neutral-400" />
        </div>
      </div>
    </aside>
  );
}
