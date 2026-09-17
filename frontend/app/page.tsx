"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  ExternalLink,
  Flame,
  Layers,
  Radio,
  RefreshCw,
  Server,
  ShieldAlert,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import AppShell from "../components/AppShell";
import { Alert, AnalyticsSummary, api, Incident, Service } from "../lib/api";
import { wsClient } from "../lib/websocket";

const SEV_BADGES: Record<string, { bg: string; text: string; border: string }> = {
  SEV1: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
  SEV2: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200" },
  SEV3: { bg: "bg-amber-50", text: "text-amber-800", border: "border-amber-200" },
  SEV4: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
};

const STATUS_BADGES: Record<string, { bg: string; text: string; border: string }> = {
  DETECTED: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200" },
  TRIGGERED: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
  ACKNOWLEDGED: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
  INVESTIGATING: { bg: "bg-amber-50", text: "text-amber-800", border: "border-amber-200" },
  MITIGATING: { bg: "bg-sky-50", text: "text-sky-700", border: "border-sky-200" },
  RESOLVED: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200" },
  CLOSED: { bg: "bg-slate-50", text: "text-slate-600", border: "border-slate-200" },
};

export default function DashboardPage() {
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [criticalAlerts, setCriticalAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async () => {
    try {
      const [anData, incData, srvData, altData] = await Promise.all([
        api.getAnalyticsSummary(14).catch(() => null),
        api.listIncidents({ limit: "6" }).catch(() => []),
        api.listServices().catch(() => []),
        api.listAlerts({ status: "OPEN", limit: "5" }).catch(() => []),
      ]);

      if (anData) setAnalytics(anData);
      setIncidents(incData);
      setServices(srvData);
      setCriticalAlerts(altData);
    } catch (err) {
      // ignore
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();

    // Subscribe to live dashboard events
    const disconnect = wsClient.connect("dashboard", () => {
      fetchData();
    });

    return () => disconnect();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchData();
  };

  const activeIncidents = incidents.filter((i) => i.status !== "RESOLVED" && i.status !== "CLOSED");
  const sev1Count = activeIncidents.filter((i) => i.severity === "SEV1").length;
  const healthyCount = services.filter((s) => s.status === "HEALTHY").length;
  const degradedServices = services.filter((s) => s.status !== "HEALTHY");

  // Chart data
  const trendData = analytics?.incident_trends?.slice(-7) || [
    { date: "Day 1", count: 2, sev1: 0, sev2: 1, sev3: 1, sev4: 0 },
    { date: "Day 2", count: 1, sev1: 0, sev2: 0, sev3: 1, sev4: 0 },
    { date: "Day 3", count: 4, sev1: 1, sev2: 1, sev3: 2, sev4: 0 },
    { date: "Day 4", count: 3, sev1: 0, sev2: 2, sev3: 1, sev4: 0 },
    { date: "Day 5", count: 5, sev1: 1, sev2: 1, sev3: 2, sev4: 1 },
    { date: "Day 6", count: 2, sev1: 0, sev2: 1, sev3: 1, sev4: 0 },
    { date: "Today", count: 3, sev1: 1, sev2: 1, sev3: 1, sev4: 0 },
  ];

  return (
    <AppShell
      title="Operations Command Center"
      subtitle="Real-Time SRE Telemetry & AIOps"
      activeIncidentsCount={activeIncidents.length}
      openAlertsCount={criticalAlerts.length}
      onIncidentCreated={fetchData}
    >
      <div className="space-y-6">
        {/* Top Control Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-slate-200">
          <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
            <span className="flex items-center gap-1.5 font-semibold text-green-700">
              <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse-slow"></span>
              AIOps Engine Active
            </span>
            <span>•</span>
            <span>Correlation Window: <strong>14 Days</strong></span>
            <span>•</span>
            <span>Services: <strong className="text-slate-800">{services.length} registered</strong></span>
          </div>

          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors shadow-2xs self-start sm:self-auto"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-slate-500 ${refreshing ? "animate-spin text-blue-600" : ""}`} />
            Refresh Telemetry
          </button>
        </div>

        {/* Critical Alert Banner (if active SEV1 or degraded services) */}
        {sev1Count > 0 && (
          <div className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50 p-4 shadow-xs">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-600 text-white shadow-2xs shrink-0 animate-pulse-slow">
                <Flame className="h-5 w-5" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-red-900">
                  {sev1Count} Critical SEV1 Outage in Progress
                </h4>
                <p className="text-xs text-red-700">
                  Customer-impacting service disruption requires immediate incident commander response.
                </p>
              </div>
            </div>
            <Link
              href="/incidents"
              className="flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 transition-colors shadow-2xs shrink-0"
            >
              Enter War Room <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}

        {/* Degraded Services Notice */}
        {degradedServices.length > 0 && sev1Count === 0 && (
          <div className="flex items-center justify-between rounded-xl border border-amber-200 bg-amber-50 p-3.5 text-xs text-amber-900 shadow-xs">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
              <span>
                <strong>Service Health Degradation:</strong> {degradedServices.length} service{degradedServices.length > 1 ? "s" : ""} currently failing probes:{" "}
                <span className="font-mono font-semibold text-amber-800">
                  {degradedServices.map((s) => `${s.name} (${s.status})`).join(", ")}
                </span>
              </span>
            </div>
            <Link
              href="/services"
              className="flex items-center gap-1 font-semibold text-blue-700 hover:text-blue-900 hover:underline shrink-0"
            >
              Inspect Services <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        )}

        {/* 4 Hero KPI Cards */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Active Incidents */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-all">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-medium">Active Incidents</span>
              <span className="flex h-6 w-6 items-center justify-center rounded-md bg-red-50 text-red-600 font-bold text-xs">
                {activeIncidents.length}
              </span>
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {activeIncidents.length}
              </span>
              <span className="text-[11px] font-mono text-slate-500">
                ({sev1Count} SEV1, {activeIncidents.filter(i => i.severity === "SEV2").length} SEV2)
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              <span>Total recorded</span>
              <span className="font-semibold text-slate-700">{analytics?.total_incidents ?? incidents.length}</span>
            </div>
          </div>

          {/* Service Availability */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-all">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-medium">Service Uptime</span>
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {services.length > 0 ? ((healthyCount / services.length) * 100).toFixed(1) : "99.9"}%
              </span>
              <span className="text-[11px] font-mono text-green-700 bg-green-50 px-1.5 py-0.5 rounded border border-green-200 font-semibold">
                {healthyCount}/{services.length} Healthy
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              <span>Degraded services</span>
              <span className={`font-semibold ${degradedServices.length > 0 ? "text-amber-700" : "text-green-700"}`}>
                {degradedServices.length}
              </span>
            </div>
          </div>

          {/* MTTA Response Time */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-all">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-medium">MTTA (Mean Time to Ack)</span>
              <Clock className="h-4 w-4 text-blue-600" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-blue-600">
                {analytics?.mtta?.mean_minutes?.toFixed(1) ?? "3.4"}m
              </span>
              <span className="text-[11px] text-slate-500 font-medium">Target: &lt;5.0m</span>
            </div>
            <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              <span>SLA Compliance</span>
              <span className="font-semibold text-green-700">96.8% In-Spec</span>
            </div>
          </div>

          {/* MTTR Resolution Time */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-all">
            <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
              <span className="font-medium">MTTR (Mean Time to Resolve)</span>
              <Zap className="h-4 w-4 text-indigo-600" />
            </div>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-bold tracking-tight text-slate-900">
                {analytics?.mttr?.median_minutes?.toFixed(0) ?? "24"}m
              </span>
              <span className="text-[11px] font-mono text-slate-500">
                P95: {analytics?.mttr?.p95_minutes?.toFixed(0) ?? "45"}m
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500 border-t border-slate-100 pt-2">
              <span>Signal/Noise Ratio</span>
              <span className="font-semibold text-blue-700">
                {analytics?.alert_to_incident_ratio ? `${analytics.alert_to_incident_ratio.toFixed(1)}:1` : "6.2:1"}
              </span>
            </div>
          </div>
        </div>

        {/* Middle Section: Active Incident Queue & Services Radar */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left 2 Cols: Active Incident Queue */}
          <div className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between pb-3 mb-4 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-red-600" />
                <h3 className="text-sm font-bold text-slate-900">Active Incident Triage Queue</h3>
              </div>
              <Link
                href="/incidents"
                className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                View all ({incidents.length}) <ArrowUpRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            {activeIncidents.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-50 text-green-600 mb-2 border border-green-100">
                  <CheckCircle2 className="h-6 w-6" />
                </div>
                <h4 className="text-sm font-semibold text-slate-800">All Systems Normal</h4>
                <p className="text-xs text-slate-500 mt-1 max-w-xs">
                  No active incidents currently undergoing triage or investigation. All SLA requirements satisfied.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-slate-100 overflow-x-auto">
                {activeIncidents.slice(0, 5).map((inc) => {
                  const sev = SEV_BADGES[inc.severity] || SEV_BADGES.SEV3;
                  const st = STATUS_BADGES[inc.status] || STATUS_BADGES.DETECTED;
                  const timeAgo = new Date(inc.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

                  return (
                    <div
                      key={inc.id}
                      className="py-3 flex items-center justify-between gap-4 hover:bg-slate-50/70 px-2 rounded-lg transition-colors group"
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Severity Tag */}
                        <span className={`rounded-md border px-2 py-0.5 text-[11px] font-bold font-mono shrink-0 ${sev.bg} ${sev.text} ${sev.border}`}>
                          {inc.severity}
                        </span>

                        <div className="min-w-0">
                          <Link
                            href={`/incidents/${inc.id}`}
                            className="text-xs font-semibold text-slate-900 hover:text-blue-600 truncate block group-hover:text-blue-600 transition-colors"
                          >
                            {inc.title}
                          </Link>
                          <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-500 font-mono">
                            <span className="font-semibold text-slate-700">{inc.service_name || "Platform"}</span>
                            <span>•</span>
                            <span>Detected at {timeAgo}</span>
                            {inc.assignee_name && (
                              <>
                                <span>•</span>
                                <span className="text-slate-600">Commander: {inc.assignee_name}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2.5 shrink-0">
                        <span className={`rounded border px-2 py-0.5 text-[10px] font-mono font-medium ${st.bg} ${st.text} ${st.border}`}>
                          {inc.status}
                        </span>
                        <Link
                          href={`/incidents/${inc.id}`}
                          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 transition-colors"
                        >
                          War Room
                        </Link>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Col: Monitored Services Radar */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Layers className="h-5 w-5 text-blue-600" />
                  <h3 className="text-sm font-bold text-slate-900">Service Health Radar</h3>
                </div>
                <Link
                  href="/services"
                  className="text-xs font-semibold text-blue-600 hover:text-blue-800 flex items-center gap-1"
                >
                  Topology <ArrowUpRight className="h-3 w-3" />
                </Link>
              </div>

              <div className="space-y-2.5">
                {services.slice(0, 5).map((srv) => (
                  <div
                    key={srv.id}
                    className="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50/50 p-2.5 hover:bg-slate-50 transition-colors"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`h-2.5 w-2.5 rounded-full shrink-0 ${
                          srv.status === "HEALTHY"
                            ? "bg-green-500"
                            : srv.status === "DEGRADED"
                            ? "bg-amber-500"
                            : "bg-red-500"
                        }`}
                      />
                      <div className="min-w-0">
                        <Link
                          href={`/services/${srv.id}`}
                          className="text-xs font-semibold text-slate-800 hover:text-blue-600 truncate block"
                        >
                          {srv.name}
                        </Link>
                        <span className="text-[10px] font-mono text-slate-500 uppercase">
                          {srv.criticality} Tier
                        </span>
                      </div>
                    </div>

                    <div className="text-right shrink-0">
                      <span className="text-xs font-mono font-bold text-slate-800">
                        {srv.uptime_percentage ? `${srv.uptime_percentage.toFixed(2)}%` : "99.9%"}
                      </span>
                      <p className="text-[10px] font-mono text-slate-500">
                        {srv.avg_response_time_ms ? `${Math.round(srv.avg_response_time_ms)}ms` : "18ms"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Health probe interval: <strong>30s</strong></span>
              <span className="font-mono text-green-700 font-semibold">100% Probed</span>
            </div>
          </div>
        </div>

        {/* Charts Section */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Incident Trends Area Chart */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Incident Trends (7-Day Velocity)</h3>
                <p className="text-xs text-slate-500">Daily frequency stratified by severity impact</p>
              </div>
              <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                Last 7 Days
              </span>
            </div>

            <div className="h-60 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorInc" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#2563eb" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#2563eb" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#ffffff",
                      borderColor: "#e2e8f0",
                      borderRadius: "0.5rem",
                      boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.08)",
                      fontSize: "12px",
                      color: "#0f172a",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#2563eb"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorInc)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Severity Breakdown Bar Chart */}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Severity Distribution</h3>
                <p className="text-xs text-slate-500">Impact distribution across current reporting cycle</p>
              </div>
              <span className="text-xs font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                Total: {incidents.length}
              </span>
            </div>

            <div className="h-60 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[
                    { name: "SEV1", count: incidents.filter((i) => i.severity === "SEV1").length, color: "#dc2626" },
                    { name: "SEV2", count: incidents.filter((i) => i.severity === "SEV2").length, color: "#ea580c" },
                    { name: "SEV3", count: incidents.filter((i) => i.severity === "SEV3").length, color: "#d97706" },
                    { name: "SEV4", count: incidents.filter((i) => i.severity === "SEV4").length, color: "#2563eb" },
                  ]}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="name" stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#ffffff",
                      borderColor: "#e2e8f0",
                      borderRadius: "0.5rem",
                      boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.08)",
                      fontSize: "12px",
                      color: "#0f172a",
                    }}
                  />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {[{ color: "#dc2626" }, { color: "#ea580c" }, { color: "#d97706" }, { color: "#2563eb" }].map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Quick Launch Dock */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
              <Zap className="h-4 w-4 text-blue-600" />
              <span>SRE Quick Actions</span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <Link
                href="/incidents"
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 shadow-2xs"
              >
                Triage Incident Queue
              </Link>
              <Link
                href="/alerts"
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 shadow-2xs"
              >
                Inspect Correlated Alerts
              </Link>
              <Link
                href="/logs"
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 shadow-2xs"
              >
                Open Log Explorer
              </Link>
              <Link
                href="/runbooks"
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 hover:text-slate-900 shadow-2xs"
              >
                View Mitigation Runbooks
              </Link>
              <Link
                href="/analytics"
                className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100/70 shadow-2xs"
              >
                SRE Reliability Analytics
              </Link>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
