"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertTriangle,
  ArrowUpDown,
  CheckCircle2,
  Clock,
  Filter,
  Flame,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";

import AppShell from "../../components/AppShell";
import { api, Incident, Service } from "../../lib/api";
import { wsClient } from "../../lib/websocket";

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

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const [serviceFilter, setServiceFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const fetchIncidents = async () => {
    try {
      const params: Record<string, string> = {};
      if (statusFilter !== "ALL") params.status = statusFilter;
      if (severityFilter !== "ALL") params.severity = severityFilter;
      if (serviceFilter !== "ALL") params.service_id = serviceFilter;
      if (searchQuery) params.search = searchQuery;

      const [incData, srvData] = await Promise.all([
        api.listIncidents(params),
        api.listServices(),
      ]);
      setIncidents(incData);
      setServices(srvData);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIncidents();
    const disconnect = wsClient.connect("dashboard", () => {
      fetchIncidents();
    });
    return () => disconnect();
  }, [statusFilter, severityFilter, serviceFilter, searchQuery]);

  const activeCount = incidents.filter((i) => i.status !== "RESOLVED" && i.status !== "CLOSED").length;

  return (
    <AppShell
      title="Incident Management"
      subtitle="Directory & Triage Queue"
      activeIncidentsCount={activeCount}
      onIncidentCreated={fetchIncidents}
    >
      <div className="space-y-6">
        {/* Status Pipeline Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-200 pb-3">
          {[
            { id: "ALL", label: "All Incidents" },
            { id: "ACTIVE", label: "Active Triage" },
            { id: "INVESTIGATING", label: "Investigating" },
            { id: "MITIGATING", label: "Mitigating" },
            { id: "RESOLVED", label: "Resolved" },
            { id: "CLOSED", label: "Closed" },
          ].map((tab) => {
            const isActive =
              statusFilter === tab.id ||
              (tab.id === "ACTIVE" && ["DETECTED", "TRIGGERED", "ACKNOWLEDGED", "INVESTIGATING", "MITIGATING"].includes(statusFilter));

            const count =
              tab.id === "ALL"
                ? incidents.length
                : tab.id === "ACTIVE"
                ? incidents.filter((i) => !["RESOLVED", "CLOSED"].includes(i.status)).length
                : incidents.filter((i) => i.status === tab.id).length;

            return (
              <button
                key={tab.id}
                onClick={() => {
                  if (tab.id === "ACTIVE") setStatusFilter("INVESTIGATING");
                  else setStatusFilter(tab.id);
                }}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700 border border-blue-200"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                <span>{tab.label}</span>
                <span
                  className={`rounded-full px-1.5 py-0.2 text-[10px] font-mono ${
                    isActive ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Filter Controls Bar */}
        <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          {/* Search Box */}
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by title, service, keyword, or symptoms..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-8 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-100 transition-all"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Severity & Service Selectors */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Severity Filter */}
            <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 bg-slate-50/70">
              {["ALL", "SEV1", "SEV2", "SEV3", "SEV4"].map((sev) => (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  className={`rounded px-2.5 py-1 text-[11px] font-mono font-semibold transition-all ${
                    severityFilter === sev
                      ? sev === "SEV1"
                        ? "bg-red-600 text-white shadow-2xs"
                        : sev === "SEV2"
                        ? "bg-orange-500 text-white shadow-2xs"
                        : sev === "SEV3"
                        ? "bg-amber-500 text-white shadow-2xs"
                        : sev === "SEV4"
                        ? "bg-blue-600 text-white shadow-2xs"
                        : "bg-white text-slate-900 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>

            {/* Service Select */}
            <select
              value={serviceFilter}
              onChange={(e) => setServiceFilter(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 focus:border-blue-600 focus:outline-none"
            >
              <option value="ALL">All Services ({services.length})</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Incident Directory Table */}
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xs">
          {loading ? (
            <div className="p-12 text-center text-xs text-slate-400 font-mono">
              Loading incident directory...
            </div>
          ) : incidents.length === 0 ? (
            <div className="p-12 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-50 text-slate-400 border border-slate-200 mb-3">
                <CheckCircle2 className="h-6 w-6 text-green-600" />
              </div>
              <h4 className="text-sm font-bold text-slate-800">No Incidents Found</h4>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                No incidents match the active search and severity filters.
              </p>
            </div>
          ) : (
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/70 font-mono text-[11px] text-slate-500">
                  <th className="py-3 px-4 font-semibold">SEVERITY</th>
                  <th className="py-3 px-4 font-semibold">INCIDENT / TITLE</th>
                  <th className="py-3 px-4 font-semibold">SERVICE</th>
                  <th className="py-3 px-4 font-semibold">STATUS</th>
                  <th className="py-3 px-4 font-semibold">COMMANDER</th>
                  <th className="py-3 px-4 font-semibold">DETECTED</th>
                  <th className="py-3 px-4 font-semibold text-right">WAR ROOM</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {incidents.map((inc) => {
                  const sev = SEV_BADGES[inc.severity] || SEV_BADGES.SEV3;
                  const st = STATUS_BADGES[inc.status] || STATUS_BADGES.DETECTED;
                  const detectedDate = new Date(inc.created_at);

                  return (
                    <tr
                      key={inc.id}
                      className="hover:bg-slate-50/80 transition-colors group"
                    >
                      {/* Severity */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-bold font-mono ${sev.bg} ${sev.text} ${sev.border}`}>
                          {inc.severity === "SEV1" && (
                            <span className="h-1.5 w-1.5 rounded-full bg-red-600 animate-pulse-slow"></span>
                          )}
                          {inc.severity}
                        </span>
                      </td>

                      {/* Title & Description */}
                      <td className="py-3 px-4 min-w-[280px]">
                        <Link
                          href={`/incidents/${inc.id}`}
                          className="font-semibold text-slate-900 group-hover:text-blue-600 transition-colors block leading-snug"
                        >
                          {inc.title}
                        </Link>
                        {inc.description && (
                          <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5">
                            {inc.description}
                          </p>
                        )}
                      </td>

                      {/* Service */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className="font-mono text-xs font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                          {inc.service_name || "Platform"}
                        </span>
                      </td>

                      {/* Status */}
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className={`inline-block rounded border px-2 py-0.5 text-[11px] font-mono font-semibold ${st.bg} ${st.text} ${st.border}`}>
                          {inc.status}
                        </span>
                      </td>

                      {/* Assignee / Commander */}
                      <td className="py-3 px-4 whitespace-nowrap text-slate-700">
                        {inc.assignee_name ? (
                          <div className="flex items-center gap-1.5">
                            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-100 text-blue-700 text-[10px] font-bold">
                              {inc.assignee_name[0]}
                            </div>
                            <span className="font-medium">{inc.assignee_name}</span>
                          </div>
                        ) : (
                          <span className="text-slate-400 font-mono text-[11px] italic">Unassigned</span>
                        )}
                      </td>

                      {/* Detected Time */}
                      <td className="py-3 px-4 whitespace-nowrap font-mono text-[11px] text-slate-500">
                        {detectedDate.toLocaleDateString()} {detectedDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </td>

                      {/* Action */}
                      <td className="py-3 px-4 whitespace-nowrap text-right">
                        <Link
                          href={`/incidents/${inc.id}`}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 transition-colors shadow-2xs"
                        >
                          War Room
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </AppShell>
  );
}
