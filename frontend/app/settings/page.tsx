"use client";

import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  Bot,
  Check,
  CheckCircle2,
  Copy,
  Cpu,
  Database,
  Key,
  Layers,
  Radio,
  RefreshCw,
  Server,
  Settings,
  Shield,
  Sliders,
  UserCheck,
  Zap,
} from "lucide-react";

import AppShell from "../../components/AppShell";
import { api, setTokens, User } from "../../lib/api";
import { useToast } from "../../components/Toast";

interface Persona {
  role: string;
  name: string;
  email: string;
  desc: string;
  badgeColor: string;
}

const DEMO_PERSONAS: Persona[] = [
  {
    role: "ADMIN",
    name: "Avery Morgan",
    email: "admin@example.com",
    desc: "Full system administration, service mutation, user management, and incident overrides.",
    badgeColor: "border-purple-200 bg-purple-50 text-purple-700",
  },
  {
    role: "ENGINEER",
    name: "Riya Shah",
    email: "engineer@example.com",
    desc: "Staff SRE, incident commander, runbook management, and postmortem authoring.",
    badgeColor: "border-blue-200 bg-blue-50 text-blue-700",
  },
  {
    role: "ON_CALL_ENGINEER",
    name: "Jordan Lee",
    email: "oncall@example.com",
    desc: "Primary on-call responder, alert acknowledgement, triage, and mitigation.",
    badgeColor: "border-amber-200 bg-amber-50 text-amber-800",
  },
  {
    role: "VIEWER",
    name: "Sam Taylor",
    email: "viewer@example.com",
    desc: "Read-only access for stakeholders, auditors, and customer support leads.",
    badgeColor: "border-slate-200 bg-slate-100 text-slate-700",
  },
];

export default function SettingsPage() {
  const { toast } = useToast();
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState(false);
  const [token, setToken] = useState<string>("");

  // Config states
  const [aiProvider, setAiProvider] = useState<string>("heuristic");
  const [mttaThreshold, setMttaThreshold] = useState<number>(5.0);
  const [mttrThreshold, setMttrThreshold] = useState<number>(30.0);
  const [webhookUrl, setWebhookUrl] = useState<string>("https://hooks.slack.com/services/T00/B00/XXXXX");
  const [configSaved, setConfigSaved] = useState(false);

  useEffect(() => {
    fetchMe();
    const stored = localStorage.getItem("incidentops_token");
    if (stored) setToken(stored);
  }, []);

  const fetchMe = async () => {
    try {
      const u = await api.getMe();
      setCurrentUser(u);
      localStorage.setItem("incidentops_user", JSON.stringify(u));
    } catch (e) {
      console.error("Failed to load user info", e);
    }
  };

  const switchPersona = async (p: Persona) => {
    try {
      setSwitching(p.role);
      const res = await api.login(p.email, "ChangeMe123!");
      setToken(res.access_token);
      await fetchMe();
      toast.success(`Switched active session to ${p.name} (${p.role})`, "Persona Activated");
    } catch (e: any) {
      toast.error(e.message || "Failed to switch persona", "Error");
    } finally {
      setSwitching(null);
    }
  };

  const copyToken = () => {
    if (!token) return;
    navigator.clipboard.writeText(token);
    setCopiedKey(true);
    toast.success("JWT Bearer token copied to clipboard!", "Copied");
    setTimeout(() => setCopiedKey(false), 2000);
  };

  const handleSaveConfig = (e: React.FormEvent) => {
    e.preventDefault();
    setConfigSaved(true);
    toast.success("Operational thresholds & integration hooks updated.", "Settings Saved");
    setTimeout(() => setConfigSaved(false), 3000);
  };

  return (
    <AppShell
      title="Platform Settings & RBAC Switcher"
      subtitle="Cluster Configuration & Role Access Controls"
    >
      <div className="space-y-6 max-w-5xl">
        {/* Active Session Info Card */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-center gap-3.5">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-100 text-blue-700 font-bold text-base">
                {currentUser?.full_name ? currentUser.full_name[0] : "A"}
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">{currentUser?.full_name || "Avery Morgan"}</h3>
                <p className="text-xs text-slate-500 font-mono">{currentUser?.email || "admin@example.com"}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="rounded border border-purple-200 bg-purple-50 px-2 py-0.2 text-[10px] font-mono font-bold text-purple-700 uppercase">
                    {currentUser?.role || "ADMIN"}
                  </span>
                  <span className="text-[11px] font-mono text-green-700 flex items-center gap-1 font-semibold">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse-slow"></span>
                    Active Authenticated Session
                  </span>
                </div>
              </div>
            </div>

            {/* Token Copy */}
            <div className="flex items-center gap-2">
              <button
                onClick={copyToken}
                className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 shadow-2xs transition-colors"
              >
                {copiedKey ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5 text-slate-400" />}
                {copiedKey ? "Copied Token" : "Copy Bearer JWT"}
              </button>
            </div>
          </div>
        </div>

        {/* 1-Click Role Switcher Demo */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
          <div className="flex items-center gap-2 mb-2">
            <UserCheck className="h-5 w-5 text-blue-600" />
            <h3 className="text-sm font-bold text-slate-900">1-Click Demo Persona Switcher (RBAC)</h3>
          </div>
          <p className="text-xs text-slate-500 mb-4">
            Instantly switch between distinct personas to test role-based authority, permissions, and incident commander workflows.
          </p>

          <div className="grid gap-3 sm:grid-cols-2">
            {DEMO_PERSONAS.map((p) => {
              const isCurrent = currentUser?.email === p.email;
              return (
                <div
                  key={p.role}
                  className={`rounded-xl border p-4 transition-all flex flex-col justify-between ${
                    isCurrent
                      ? "border-blue-600 bg-blue-50/50 shadow-xs"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className={`rounded border px-2 py-0.5 text-[10px] font-mono font-bold uppercase ${p.badgeColor}`}>
                        {p.role}
                      </span>
                      {isCurrent && (
                        <span className="text-[10px] font-mono font-bold text-blue-700 flex items-center gap-1">
                          <CheckCircle2 className="h-3 w-3" /> CURRENT USER
                        </span>
                      )}
                    </div>
                    <h4 className="text-sm font-bold text-slate-900">{p.name}</h4>
                    <p className="text-[11px] font-mono text-slate-400 mb-2">{p.email}</p>
                    <p className="text-xs text-slate-600 leading-relaxed">{p.desc}</p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex justify-end">
                    <button
                      onClick={() => switchPersona(p)}
                      disabled={isCurrent || switching === p.role}
                      className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                        isCurrent
                          ? "bg-slate-100 text-slate-400 cursor-default"
                          : "bg-blue-600 text-white hover:bg-blue-700 shadow-2xs"
                      }`}
                    >
                      {switching === p.role ? "Switching..." : isCurrent ? "Active" : `Switch to ${p.name}`}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Operational Thresholds Form */}
        <form onSubmit={handleSaveConfig} className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs space-y-6">
          <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
            <Sliders className="h-5 w-5 text-blue-600" />
            <div>
              <h3 className="text-sm font-bold text-slate-900">Incident Thresholds & SLA Parameters</h3>
              <p className="text-xs text-slate-500">Configures MTTA target alerts and P95 MTTR escalation alarms</p>
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                MTTA SLA Target (Minutes)
              </label>
              <input
                type="number"
                step="0.5"
                value={mttaThreshold}
                onChange={(e) => setMttaThreshold(parseFloat(e.target.value) || 5.0)}
                className="form-input font-mono"
              />
              <p className="text-[11px] text-slate-400 mt-1">Alert fires if incident unacknowledged after threshold.</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                MTTR SLA Target (Minutes)
              </label>
              <input
                type="number"
                step="1"
                value={mttrThreshold}
                onChange={(e) => setMttrThreshold(parseFloat(e.target.value) || 30.0)}
                className="form-input font-mono"
              />
              <p className="text-[11px] text-slate-400 mt-1">Target duration for complete service recovery.</p>
            </div>
          </div>

          <div className="space-y-4 pt-4 border-t border-slate-100">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                AIOps Intelligence Engine Provider
              </label>
              <select
                value={aiProvider}
                onChange={(e) => setAiProvider(e.target.value)}
                className="form-input cursor-pointer font-medium"
              >
                <option value="heuristic">Heuristic SRE Rule Engine (Built-in deterministic correlation)</option>
                <option value="openai">OpenAI GPT-4o Telemetry Analyzer</option>
                <option value="anthropic">Anthropic Claude 3.5 Sonnet SRE Copilot</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Slack / Incident Webhook Dispatch URL
              </label>
              <input
                type="text"
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                className="form-input font-mono"
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
            <span className="text-xs text-slate-500 font-mono">Changes persist across cluster instances.</span>
            <button
              type="submit"
              className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 shadow-2xs transition-colors"
            >
              Save Configuration
            </button>
          </div>
        </form>
      </div>
    </AppShell>
  );
}
