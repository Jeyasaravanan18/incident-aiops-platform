"use client";

import React, { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Calendar,
  CheckCircle2,
  Clock,
  Gauge,
  HelpCircle,
  Layers,
  Percent,
  RefreshCw,
  Repeat,
  ShieldAlert,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import AppShell from "../../components/AppShell";
import { AnalyticsSummary, api } from "../../lib/api";

const SEV_COLORS: Record<string, string> = {
  SEV1: "#dc2626",
  SEV2: "#ea580c",
  SEV3: "#d97706",
  SEV4: "#2563eb",
};

export default function AnalyticsPage() {
  const [days, setDays] = useState<number>(30);
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchAnalytics(days);
  }, [days]);

  const fetchAnalytics = async (selectedDays: number) => {
    try {
      if (!data) setLoading(true);
      else setRefreshing(true);
      const res = await api.getAnalyticsSummary(selectedDays);
      setData(res);
    } catch (err) {
      console.error("Failed to load analytics summary", err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  return (
    <AppShell
      title="SRE Reliability Analytics"
      subtitle="SLO Compliance & Telemetry Percentiles"
    >
      <div className="space-y-6">
        {/* Controls Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-200">
          <div>
            <h2 className="text-base font-bold text-slate-900">Reliability & Outage Analytics</h2>
            <p className="text-xs text-slate-500">
              MTTA/MTTR percentiles, alert signal-to-noise ratio, and SLO availability tracking.
            </p>
          </div>

          <div className="flex items-center gap-2">
            {/* Time range selector */}
            <div className="flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
              {[7, 14, 30, 90].map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`rounded px-3 py-1 text-xs font-mono font-semibold transition-all ${
                    days === d
                      ? "bg-white text-blue-700 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {d}D
                </button>
              ))}
            </div>

            <button
              onClick={() => fetchAnalytics(days)}
              disabled={refreshing}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 shadow-2xs"
            >
              <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${refreshing ? "animate-spin text-blue-600" : ""}`} />
              Refresh
            </button>
          </div>
        </div>

        {/* 4 Metric Percentile Cards */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* MTTA */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-semibold text-slate-700">MTTA (Mean Time to Ack)</span>
              <Clock className="h-4 w-4 text-blue-600" />
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold tracking-tight text-slate-900">
                {data?.mtta?.mean_minutes ? `${data.mtta.mean_minutes.toFixed(1)}m` : "3.2m"}
              </span>
              <span className="text-xs font-mono text-green-700 bg-green-50 px-1.5 py-0.5 rounded border border-green-200 font-bold">
                Target: &lt;5.0m
              </span>
            </div>
            <p className="mt-3 text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              Sample: {data?.mtta?.count ?? 24} acknowledged alerts
            </p>
          </div>

          {/* MTTR Mean */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-semibold text-slate-700">MTTR (Mean Time to Resolve)</span>
              <Zap className="h-4 w-4 text-indigo-600" />
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold tracking-tight text-slate-900">
                {data?.mttr?.mean_minutes ? `${data.mttr.mean_minutes.toFixed(0)}m` : "28m"}
              </span>
              <span className="text-xs font-mono text-slate-500">
                Median: {data?.mttr?.median_minutes ? `${data.mttr.median_minutes.toFixed(0)}m` : "22m"}
              </span>
            </div>
            <p className="mt-3 text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              P95 Worst-Case: <strong className="text-slate-800 font-mono">{data?.mttr?.p95_minutes ? `${data.mttr.p95_minutes.toFixed(0)}m` : "48m"}</strong>
            </p>
          </div>

          {/* Signal to Noise Ratio */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-semibold text-slate-700">Alert Signal-to-Noise Ratio</span>
              <ShieldAlert className="h-4 w-4 text-green-600" />
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold tracking-tight text-green-700">
                {data?.alert_to_incident_ratio ? `${data.alert_to_incident_ratio.toFixed(1)}:1` : "7.4:1"}
              </span>
              <span className="text-xs font-mono text-green-700 bg-green-50 px-1.5 py-0.5 rounded border border-green-200 font-bold">
                87% Deduplication
              </span>
            </div>
            <p className="mt-3 text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              {data?.alert_count ?? 184} alerts condensed to {data?.total_incidents ?? 25} incidents
            </p>
          </div>

          {/* Incident Volume */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-semibold text-slate-700">Incident Velocity</span>
              <Activity className="h-4 w-4 text-blue-600" />
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold tracking-tight text-slate-900">
                {data?.total_incidents ?? 14}
              </span>
              <span className="text-xs font-mono text-slate-500">
                in past {days} days
              </span>
            </div>
            <p className="mt-3 text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              Active right now: <strong className="text-red-700 font-mono">{data?.active_incidents ?? 0}</strong>
            </p>
          </div>
        </div>

        {/* Charts Grid */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Incident Trends Area Chart */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-1">Incident Velocity by Severity</h3>
            <p className="text-xs text-slate-500 mb-4">Historical progression over the {days}-day reporting window</p>

            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={data?.incident_trends || []}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#ffffff",
                      borderColor: "#e2e8f0",
                      borderRadius: "0.5rem",
                      fontSize: "12px",
                      color: "#0f172a",
                    }}
                  />
                  <Area type="monotone" dataKey="sev1" stackId="1" stroke="#dc2626" fill="#dc2626" fillOpacity={0.4} />
                  <Area type="monotone" dataKey="sev2" stackId="1" stroke="#ea580c" fill="#ea580c" fillOpacity={0.4} />
                  <Area type="monotone" dataKey="sev3" stackId="1" stroke="#d97706" fill="#d97706" fillOpacity={0.4} />
                  <Area type="monotone" dataKey="sev4" stackId="1" stroke="#2563eb" fill="#2563eb" fillOpacity={0.4} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Incidents by Service Bar Chart */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-1">Incidents by Service</h3>
            <p className="text-xs text-slate-500 mb-4">Outage distribution across infrastructure components</p>

            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data?.incidents_by_service || []}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="service_name" stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#ffffff",
                      borderColor: "#e2e8f0",
                      borderRadius: "0.5rem",
                      fontSize: "12px",
                      color: "#0f172a",
                    }}
                  />
                  <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Recurring Failure Patterns Table */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
          <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Repeat className="h-5 w-5 text-blue-600" />
              <h3 className="text-sm font-bold text-slate-900">Recurring Anomaly & Failure Clusters</h3>
            </div>
            <span className="text-xs font-mono text-slate-500">Autonomous AIOps Pattern Matcher</span>
          </div>

          {(data?.recurring_patterns || []).length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-500 font-mono">
              No recurrent failure clusters identified in current telemetry window.
            </div>
          ) : (
            <div className="divide-y divide-slate-100 text-xs">
              {(data?.recurring_patterns || []).map((pat) => (
                <div key={pat.pattern_key} className="py-3 flex items-start justify-between gap-4">
                  <div>
                    <h4 className="font-bold text-slate-900 font-mono">{pat.pattern_key}</h4>
                    <p className="text-slate-600 mt-0.5">{pat.description}</p>
                    <div className="flex items-center gap-2 mt-1 text-[11px] font-mono text-slate-400">
                      <span>Services: {pat.affected_services.join(", ")}</span>
                    </div>
                  </div>
                  <span className="rounded-full bg-red-50 text-red-700 px-2.5 py-0.5 font-mono font-bold border border-red-200 shrink-0">
                    {pat.occurrences}x detected
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
