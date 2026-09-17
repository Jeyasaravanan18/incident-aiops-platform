"use client";

import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  Flame,
  Globe,
  Play,
  RefreshCw,
  Server,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import AppShell from "../../../components/AppShell";
import { api, HealthCheck, Incident, Service } from "../../../lib/api";
import { wsClient } from "../../../lib/websocket";

export default function ServiceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const serviceId = resolvedParams.id;

  const [service, setService] = useState<Service | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<HealthCheck | null>(null);

  const loadService = async () => {
    try {
      const [srv, incs] = await Promise.all([
        api.getService(serviceId),
        api.listIncidents({ service_id: serviceId }),
      ]);
      setService(srv);
      setIncidents(incs);
    } catch (e) {
      // ignore
    }
  };

  useEffect(() => {
    loadService();
    const disconnect = wsClient.connect(`service:${serviceId}`, () => {
      loadService();
    });
    return () => disconnect();
  }, [serviceId]);

  const handleManualProbe = async () => {
    setProbing(true);
    try {
      const res = await api.triggerHealthCheck(serviceId);
      setProbeResult(res);
      await loadService();
    } catch (err) {
      // ignore
    } finally {
      setProbing(false);
    }
  };

  if (!service) {
    return (
      <AppShell title="Service Telemetry" subtitle="Loading...">
        <div className="flex items-center justify-center py-20 font-mono text-xs text-slate-400">
          Loading service topology...
        </div>
      </AppShell>
    );
  }

  const chartData = (service.recent_health_checks || [])
    .slice(0, 15)
    .reverse()
    .map((c) => ({
      time: new Date(c.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      latency: c.response_time_ms ?? 0,
      available: c.availability ? 1 : 0,
    }));

  return (
    <AppShell
      breadcrumbs={[
        { label: "Services", href: "/services" },
        { label: service.name },
      ]}
      onIncidentCreated={loadService}
    >
      <div className="space-y-6">
        {/* Service Header Card */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span
                  className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-0.5 text-xs font-mono font-bold ${
                    service.status === "HEALTHY"
                      ? "bg-green-50 text-green-700 border-green-200"
                      : service.status === "DEGRADED"
                      ? "bg-amber-50 text-amber-800 border-amber-200"
                      : "bg-red-50 text-red-700 border-red-200"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      service.status === "HEALTHY" ? "bg-green-500" : "bg-red-500"
                    }`}
                  />
                  {service.status}
                </span>

                <span className="text-xs font-mono font-semibold bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-200">
                  {service.criticality} CRITICALITY
                </span>

                <span className="text-xs font-mono text-slate-500 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
                  Env: {service.environment}
                </span>
              </div>

              <h1 className="text-2xl font-bold text-slate-900">{service.name}</h1>
              <p className="text-xs text-slate-500 font-mono mt-0.5">{service.slug}</p>
              <p className="text-xs text-slate-600 mt-2 max-w-2xl leading-relaxed">
                {service.description || "Production service node registered for automated health check probes and anomaly detection."}
              </p>

              {service.repository && (
                <a
                  href={service.repository}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:underline mt-3 font-mono"
                >
                  <Globe className="h-3.5 w-3.5" />
                  {service.repository}
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
            </div>

            {/* Probe Action Button */}
            <div className="flex flex-col items-end gap-2 shrink-0">
              <button
                onClick={handleManualProbe}
                disabled={probing}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-2xs"
              >
                <Play className={`h-3.5 w-3.5 ${probing ? "animate-spin" : ""}`} />
                {probing ? "Probing..." : "Trigger Live Probe"}
              </button>

              {probeResult && (
                <span
                  className={`text-[11px] font-mono font-semibold ${
                    probeResult.availability ? "text-green-700" : "text-red-700"
                  }`}
                >
                  HTTP {probeResult.http_status} ({probeResult.response_time_ms}ms)
                </span>
              )}
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="grid grid-cols-3 gap-3 mt-6 pt-5 border-t border-slate-100 text-xs font-mono">
            <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
              <span className="text-[10px] text-slate-400 uppercase block">Uptime Ratio</span>
              <span className="text-lg font-bold text-slate-900">
                {service.uptime_percentage ? `${service.uptime_percentage.toFixed(2)}%` : "99.9%"}
              </span>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
              <span className="text-[10px] text-slate-400 uppercase block">Average Latency</span>
              <span className="text-lg font-bold text-blue-700">
                {service.avg_response_time_ms ? `${Math.round(service.avg_response_time_ms)}ms` : "16ms"}
              </span>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
              <span className="text-[10px] text-slate-400 uppercase block">Linked Incidents</span>
              <span className={`text-lg font-bold ${incidents.length > 0 ? "text-amber-800" : "text-slate-900"}`}>
                {incidents.length}
              </span>
            </div>
          </div>
        </div>

        {/* Latency History Chart */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Probe Response Latency (Recent 15 Probes)</h3>
              <p className="text-xs text-slate-500">Real-time roundtrip probe response in milliseconds</p>
            </div>
            <span className="text-xs font-mono text-slate-500 bg-slate-50 px-2 py-0.5 rounded border border-slate-200">
              Probe target: {service.health_endpoint || "/healthz"}
            </span>
          </div>

          <div className="h-60 w-full">
            {chartData.length === 0 ? (
              <div className="flex h-full items-center justify-center text-xs font-mono text-slate-400">
                No health check probe history recorded yet. Click "Trigger Live Probe" to run one.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="latencyGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#16a34a" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="#16a34a" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} tickLine={false} />
                  <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} unit="ms" />
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
                    dataKey="latency"
                    stroke="#16a34a"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#latencyGrad)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Associated Incidents */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
          <h3 className="text-sm font-bold text-slate-900 mb-3">Service Incident History</h3>
          {incidents.length === 0 ? (
            <div className="py-6 text-center text-xs text-slate-500 font-mono">
              No historical or active incidents recorded for this service. Clean reliability record.
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {incidents.map((inc) => (
                <div key={inc.id} className="py-3 flex items-center justify-between gap-4 hover:bg-slate-50 px-2 rounded-lg">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="rounded border border-red-200 bg-red-50 px-1.5 py-0.2 text-[10px] font-bold font-mono text-red-700">
                        {inc.severity}
                      </span>
                      <Link
                        href={`/incidents/${inc.id}`}
                        className="text-xs font-bold text-slate-900 hover:text-blue-600"
                      >
                        {inc.title}
                      </Link>
                    </div>
                    <p className="text-[11px] font-mono text-slate-400">
                      Detected at {new Date(inc.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <span className="text-xs font-mono font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                    {inc.status}
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
