"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Lock, ShieldAlert, Sparkles, UserCheck } from "lucide-react";
import { api } from "../../lib/api";

const DEMO_PERSONAS = [
  {
    role: "ADMIN",
    name: "Avery Morgan",
    email: "admin@example.com",
    badge: "Full System Authority",
    color: "border-purple-200 text-purple-700 bg-purple-50",
  },
  {
    role: "ENGINEER",
    name: "Riya Shah",
    email: "engineer@example.com",
    badge: "Staff SRE / Triage",
    color: "border-blue-200 text-blue-700 bg-blue-50",
  },
  {
    role: "ON_CALL_ENGINEER",
    name: "Jordan Lee",
    email: "oncall@example.com",
    badge: "Primary On-Call Responder",
    color: "border-amber-200 text-amber-800 bg-amber-50",
  },
  {
    role: "VIEWER",
    name: "Sam Taylor",
    email: "viewer@example.com",
    badge: "Read-Only Stakeholder",
    color: "border-slate-200 text-slate-700 bg-slate-100",
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("ChangeMe123!");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e?: React.FormEvent, targetEmail?: string) => {
    if (e) e.preventDefault();
    const loginEmail = targetEmail || email;
    setLoading(true);
    setError(null);

    try {
      await api.login(loginEmail, password);
      const me = await api.getMe();
      localStorage.setItem("incidentops_user", JSON.stringify(me));
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Failed to authenticate. Ensure backend server is running.");
    } finally {
      setLoading(false);
    }
  };

  const selectPersona = (personaEmail: string) => {
    setEmail(personaEmail);
    handleLogin(undefined, personaEmail);
  };

  return (
    <main className="flex min-h-screen bg-white text-slate-900">
      {/* Left Feature Showcase Panel */}
      <div className="hidden w-1/2 flex-col justify-between border-r border-slate-200 bg-slate-50/50 p-12 lg:flex">
        <div>
          <div className="flex items-center gap-3 text-xl font-bold tracking-tight text-slate-900">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs">
              <ShieldAlert className="h-5 w-5" />
            </div>
            <span>Incident<span className="text-blue-600">Ops</span></span>
          </div>
          <p className="mt-2 text-xs text-slate-500 font-mono">
            Enterprise SRE Incident Command & AIOps Platform
          </p>
        </div>

        <div className="space-y-6">
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <div className="flex items-center gap-2 text-xs font-mono font-semibold uppercase text-blue-600 mb-3">
              <Sparkles className="h-4 w-4" /> Production Architecture Highlights
            </div>
            <ul className="space-y-2.5 text-xs text-slate-700">
              <li className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 text-green-700 font-bold text-[10px]">✓</span>
                Fingerprint Alert Deduplication & Noise Correlation
              </li>
              <li className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 text-green-700 font-bold text-[10px]">✓</span>
                Mathematical MTTA & MTTR Percentiles (Mean, Median, P95)
              </li>
              <li className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 text-green-700 font-bold text-[10px]">✓</span>
                Strict SRE State Machine & Immutable Audit Timeline
              </li>
              <li className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 text-green-700 font-bold text-[10px]">✓</span>
                Interactive SRE Runbook Playbooks & Copilot Mitigation
              </li>
              <li className="flex items-center gap-2">
                <span className="flex h-4 w-4 items-center justify-center rounded-full bg-green-100 text-green-700 font-bold text-[10px]">✓</span>
                Blameless Postmortem Studio with Root Cause Analysis
              </li>
            </ul>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>SOC2 Type II & FedRAMP Ready</span>
            <span>Cluster v1.0.0</span>
          </div>
        </div>

        <div className="text-xs text-slate-500">
          Built for high-velocity site reliability and mission-critical operations.
        </div>
      </div>

      {/* Right Login Form Panel */}
      <div className="flex flex-1 flex-col justify-center px-6 py-12 lg:px-16">
        <div className="mx-auto w-full max-w-md space-y-6">
          <div>
            <div className="flex items-center gap-2 text-lg font-bold tracking-tight text-slate-900 lg:hidden mb-4">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white">
                <ShieldAlert className="h-4 w-4" />
              </div>
              <span>Incident<span className="text-blue-600">Ops</span></span>
            </div>

            <h2 className="text-2xl font-bold tracking-tight text-slate-900">Sign in to Operations Center</h2>
            <p className="mt-1 text-xs text-slate-500">
              Select a demo persona below or sign in with your enterprise credentials.
            </p>
          </div>

          {/* 1-Click Persona Cards */}
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase text-slate-400 font-mono">
              Quick 1-Click Demo Login
            </p>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_PERSONAS.map((p) => (
                <button
                  key={p.role}
                  type="button"
                  onClick={() => selectPersona(p.email)}
                  disabled={loading}
                  className="flex flex-col items-start rounded-lg border border-slate-200 bg-white p-2.5 text-left hover:border-blue-300 hover:bg-blue-50/40 transition-all shadow-2xs group"
                >
                  <div className="flex w-full items-center justify-between">
                    <span className={`rounded border px-1.5 py-0.2 text-[9px] font-mono font-bold uppercase ${p.color}`}>
                      {p.role}
                    </span>
                    <UserCheck className="h-3.5 w-3.5 text-slate-400 group-hover:text-blue-600" />
                  </div>
                  <p className="mt-1.5 text-xs font-bold text-slate-900 group-hover:text-blue-600">{p.name}</p>
                  <p className="text-[10px] text-slate-400 font-mono truncate w-full">{p.badge}</p>
                </button>
              ))}
            </div>
          </div>

          <div className="relative my-4 flex items-center">
            <div className="flex-grow border-t border-slate-200"></div>
            <span className="mx-3 flex-shrink text-[11px] font-mono uppercase text-slate-400">or manual auth</span>
            <div className="flex-grow border-t border-slate-200"></div>
          </div>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
              {error}
            </div>
          )}

          <form onSubmit={(e) => handleLogin(e)} className="space-y-4 text-xs">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Work Email Address</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="form-input"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="form-input pr-9"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-blue-600 py-2.5 text-xs font-semibold text-white shadow-xs hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Authenticating Session..." : "Sign in to IncidentOps"}
            </button>
          </form>

          <p className="text-center text-[11px] text-slate-400 font-mono">
            Default Demo Password: <span className="font-semibold text-slate-700">ChangeMe123!</span>
          </p>
        </div>
      </div>
    </main>
  );
}
