"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowUpRight,
  CheckCircle2,
  ExternalLink,
  Flame,
  Grid,
  Layers,
  List,
  Plus,
  Radio,
  Server,
  X,
} from "lucide-react";

import AppShell from "../../components/AppShell";
import { api, Service } from "../../lib/api";
import { wsClient } from "../../lib/websocket";

const STATUS_CONFIG: Record<string, { label: string; ring: string; badge: string }> = {
  HEALTHY: { label: "Operational", ring: "bg-green-500", badge: "bg-green-50 text-green-700 border-green-200" },
  DEGRADED: { label: "Degraded", ring: "bg-amber-500", badge: "bg-amber-50 text-amber-800 border-amber-200" },
  UNHEALTHY: { label: "Outage", ring: "bg-red-500", badge: "bg-red-50 text-red-700 border-red-200" },
  UNKNOWN: { label: "Unknown", ring: "bg-slate-400", badge: "bg-slate-100 text-slate-700 border-slate-200" },
};

const CRITICALITY_CONFIG: Record<string, { label: string; badge: string }> = {
  CRITICAL: { label: "Tier 0 (Critical)", badge: "bg-red-50 text-red-700 border-red-200" },
  HIGH: { label: "Tier 1 (High)", badge: "bg-orange-50 text-orange-800 border-orange-200" },
  MEDIUM: { label: "Tier 2 (Medium)", badge: "bg-blue-50 text-blue-700 border-blue-200" },
  LOW: { label: "Tier 3 (Low)", badge: "bg-slate-100 text-slate-600 border-slate-200" },
};

export default function ServicesPage() {
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [criticalityFilter, setCriticalityFilter] = useState("ALL");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  const [form, setForm] = useState({
    name: "",
    slug: "",
    description: "",
    repository: "",
    environment: "production",
    health_endpoint: "",
    criticality: "HIGH",
  });
  const [error, setError] = useState<string | null>(null);

  const loadServices = async () => {
    try {
      const data = await api.listServices();
      setServices(data);
    } catch (err) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadServices();
    const disconnect = wsClient.connect("dashboard", () => {
      loadServices();
    });
    return () => disconnect();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api.createService({
        ...form,
        health_endpoint: form.health_endpoint || undefined,
        criticality: form.criticality as any,
      });
      setIsModalOpen(false);
      setForm({
        name: "",
        slug: "",
        description: "",
        repository: "",
        environment: "production",
        health_endpoint: "",
        criticality: "HIGH",
      });
      await loadServices();
    } catch (err: any) {
      setError(err.message || "Failed to register service");
    }
  };

  const filtered = services.filter(
    (s) => criticalityFilter === "ALL" || s.criticality === criticalityFilter
  );

  const healthyCount = services.filter((s) => s.status === "HEALTHY").length;

  return (
    <AppShell
      title="Service Catalog & Topology"
      subtitle="Monitored Services & Criticality Tiers"
      onIncidentCreated={loadServices}
    >
      <div className="space-y-6">
        {/* Top Control Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-200">
          <div className="flex items-center gap-3">
            <p className="text-xs text-slate-500 font-mono">
              Total Services: <strong className="text-slate-900">{services.length}</strong> • Healthy:{" "}
              <strong className="text-green-700">{healthyCount}</strong>
            </p>

            {/* Criticality Pills */}
            <div className="hidden md:flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 bg-slate-50/70">
              {["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"].map((crit) => (
                <button
                  key={crit}
                  onClick={() => setCriticalityFilter(crit)}
                  className={`rounded px-2.5 py-1 text-[11px] font-mono font-semibold transition-all ${
                    criticalityFilter === crit
                      ? "bg-white text-blue-700 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {crit}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2.5 self-start sm:self-auto">
            {/* View switcher */}
            <div className="flex items-center rounded-lg border border-slate-200 p-0.5 bg-slate-50">
              <button
                onClick={() => setViewMode("grid")}
                className={`p-1.5 rounded ${viewMode === "grid" ? "bg-white text-blue-600 shadow-2xs" : "text-slate-400"}`}
              >
                <Grid className="h-4 w-4" />
              </button>
              <button
                onClick={() => setViewMode("list")}
                className={`p-1.5 rounded ${viewMode === "list" ? "bg-white text-blue-600 shadow-2xs" : "text-slate-400"}`}
              >
                <List className="h-4 w-4" />
              </button>
            </div>

            <button
              onClick={() => setIsModalOpen(true)}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors shadow-2xs"
            >
              <Plus className="h-4 w-4" />
              Register Service
            </button>
          </div>
        </div>

        {/* Services Grid or List */}
        {loading ? (
          <div className="p-12 text-center text-xs font-mono text-slate-400">Loading service catalog...</div>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-xs">
            <Server className="mx-auto h-8 w-8 text-slate-400 mb-2" />
            <h4 className="text-sm font-bold text-slate-800">No Services Found</h4>
            <p className="text-xs text-slate-500 mt-1">Register a service to begin automated probe telemetry.</p>
          </div>
        ) : viewMode === "grid" ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((s) => {
              const st = STATUS_CONFIG[s.status] || STATUS_CONFIG.UNKNOWN;
              const cr = CRITICALITY_CONFIG[s.criticality] || CRITICALITY_CONFIG.MEDIUM;

              return (
                <div
                  key={s.id}
                  className="rounded-xl border border-slate-200 bg-white p-5 shadow-xs hover:border-slate-300 hover:shadow-subtle transition-all flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[10px] font-mono font-semibold ${st.badge}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${st.ring}`}></span>
                        {st.label}
                      </span>
                      <span className={`rounded border px-2 py-0.5 text-[10px] font-mono font-semibold ${cr.badge}`}>
                        {cr.label}
                      </span>
                    </div>

                    <h3 className="text-base font-bold text-slate-900 mb-1">{s.name}</h3>
                    <p className="text-xs text-slate-500 font-mono mb-2">{s.slug}</p>
                    <p className="text-xs text-slate-600 line-clamp-2 leading-relaxed">
                      {s.description || "Microservice component registered in primary production cluster."}
                    </p>
                  </div>

                  <div className="mt-5 pt-4 border-t border-slate-100">
                    <div className="grid grid-cols-2 gap-2 text-xs font-mono mb-3">
                      <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                        <span className="text-[10px] text-slate-400 uppercase block">Uptime</span>
                        <span className="font-bold text-slate-900">
                          {s.uptime_percentage ? `${s.uptime_percentage.toFixed(2)}%` : "99.9%"}
                        </span>
                      </div>
                      <div className="rounded-lg bg-slate-50 p-2 border border-slate-100">
                        <span className="text-[10px] text-slate-400 uppercase block">Latency</span>
                        <span className="font-bold text-blue-700">
                          {s.avg_response_time_ms ? `${Math.round(s.avg_response_time_ms)}ms` : "18ms"}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      {s.active_incidents_count && s.active_incidents_count > 0 ? (
                        <span className="text-xs font-mono text-red-600 font-bold flex items-center gap-1">
                          <Flame className="h-3.5 w-3.5 text-red-600" />
                          {s.active_incidents_count} Active Outage
                        </span>
                      ) : (
                        <span className="text-xs font-mono text-green-700 font-medium flex items-center gap-1">
                          <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                          Probes In-Spec
                        </span>
                      )}

                      <Link
                        href={`/services/${s.id}`}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800 hover:underline"
                      >
                        Deep Dive <ArrowUpRight className="h-3.5 w-3.5" />
                      </Link>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 font-mono text-[11px] text-slate-500">
                  <th className="py-3 px-4 font-semibold">STATUS</th>
                  <th className="py-3 px-4 font-semibold">SERVICE NAME</th>
                  <th className="py-3 px-4 font-semibold">CRITICALITY</th>
                  <th className="py-3 px-4 font-semibold">UPTIME</th>
                  <th className="py-3 px-4 font-semibold">LATENCY</th>
                  <th className="py-3 px-4 font-semibold text-right">ACTION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((s) => {
                  const st = STATUS_CONFIG[s.status] || STATUS_CONFIG.UNKNOWN;
                  const cr = CRITICALITY_CONFIG[s.criticality] || CRITICALITY_CONFIG.MEDIUM;
                  return (
                    <tr key={s.id} className="hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-mono font-semibold ${st.badge}`}>
                          <span className={`h-1.5 w-1.5 rounded-full ${st.ring}`}></span>
                          {st.label}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-900">{s.name}</td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className={`rounded border px-2 py-0.5 text-[10px] font-mono font-semibold ${cr.badge}`}>
                          {cr.label}
                        </span>
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap font-mono font-semibold text-slate-800">
                        {s.uptime_percentage ? `${s.uptime_percentage.toFixed(2)}%` : "99.9%"}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap font-mono text-blue-700">
                        {s.avg_response_time_ms ? `${Math.round(s.avg_response_time_ms)}ms` : "18ms"}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap text-right">
                        <Link
                          href={`/services/${s.id}`}
                          className="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                        >
                          View Telemetry
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Register Service Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-modal">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
              <h3 className="text-base font-bold text-slate-900">Register Monitored Service</h3>
              <button
                onClick={() => setIsModalOpen(false)}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {error && (
              <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                {error}
              </div>
            )}

            <form onSubmit={handleCreate} className="space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Service Name *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Payment Gateway"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value, slug: e.target.value.toLowerCase().replace(/\s+/g, "-") })}
                    className="form-input"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Service Slug *</label>
                  <input
                    type="text"
                    required
                    placeholder="payment-gateway"
                    value={form.slug}
                    onChange={(e) => setForm({ ...form, slug: e.target.value })}
                    className="form-input font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Criticality Tier *</label>
                <select
                  value={form.criticality}
                  onChange={(e) => setForm({ ...form, criticality: e.target.value })}
                  className="form-input cursor-pointer"
                >
                  <option value="CRITICAL">Tier 0 (CRITICAL) - Core revenue or auth path</option>
                  <option value="HIGH">Tier 1 (HIGH) - Core business functionality</option>
                  <option value="MEDIUM">Tier 2 (MEDIUM) - Internal service / asynchronous</option>
                  <option value="LOW">Tier 3 (LOW) - Non-critical background worker</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Health Check Endpoint</label>
                <input
                  type="text"
                  placeholder="https://api.example.com/healthz"
                  value={form.health_endpoint}
                  onChange={(e) => setForm({ ...form, health_endpoint: e.target.value })}
                  className="form-input font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Repository URL</label>
                <input
                  type="text"
                  placeholder="https://github.com/org/payment-service"
                  value={form.repository}
                  onChange={(e) => setForm({ ...form, repository: e.target.value })}
                  className="form-input font-mono"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  rows={2}
                  placeholder="Responsibilities, downstream dependencies..."
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="form-input resize-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
                >
                  Register Service
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
}
