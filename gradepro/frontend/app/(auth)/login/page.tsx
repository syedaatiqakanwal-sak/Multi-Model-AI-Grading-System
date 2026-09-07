"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ClipboardCheck, ArrowRight } from "lucide-react";
import { useAuthStore } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@gradepro.ai");
  const [password, setPassword] = useState("Admin123!");
  const [loading, setLoading] = useState(false);
  const login = useAuthStore((s) => s.login);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      login("mock_token_jwt", {
        id: "00000000-0000-0000-0000-000000000001",
        name: "Sarah Johnson",
        email: email,
        role: "ADMIN",
      });
      router.push("/dashboard");
    }, 600);
  };

  return (
    <div className="min-h-screen bg-brand-black flex flex-col items-center justify-center p-6 select-none">
      <div className="w-full max-w-md bg-white rounded-3xl p-8 shadow-2xl space-y-6">
        {/* Brand */}
        <div className="flex flex-col items-center text-center">
          <div className="w-12 h-12 rounded-2xl bg-[#8b5cf6] flex items-center justify-center text-black shadow-md mb-3">
            <ClipboardCheck className="w-7 h-7 stroke-[2.5]" />
          </div>
          <h1 className="text-2xl font-extrabold text-neutral-900 tracking-tight">
            Grade<span className="text-[#8b5cf6]">Pro</span>
          </h1>
          <p className="text-xs text-neutral-500 font-medium mt-0.5">
            Smart Grading. Clear Results.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleLogin} className="space-y-4 pt-2">
          <div>
            <label className="text-xs font-bold text-neutral-700 block mb-1">Email Address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl border border-neutral-200 text-xs font-medium text-neutral-900 outline-none focus:border-[#8b5cf6] transition"
            />
          </div>

          <div>
            <label className="text-xs font-bold text-neutral-700 block mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-4 py-2.5 rounded-xl border border-neutral-200 text-xs font-medium text-neutral-900 outline-none focus:border-[#8b5cf6] transition"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl bg-[#8b5cf6] text-black font-extrabold text-xs shadow-md hover:bg-[#8b5cf6] transition flex items-center justify-center gap-2 mt-2"
          >
            <span>{loading ? "Signing in..." : "Sign In to GradePro"}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

        <p className="text-[11px] text-center text-neutral-400 font-medium">
          Protected by GradePro Multi-Layer Role Based Security
        </p>
      </div>
    </div>
  );
}
