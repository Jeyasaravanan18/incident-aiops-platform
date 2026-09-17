"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  AlertOctagon,
  AlertTriangle,
  ArrowUpRight,
  Bell,
  CheckCircle2,
  Clock,
  EyeOff,
  Filter,
  RefreshCw,
  Search,
  ShieldAlert,
  X,
} from "lucide-react";

import AppShell from "../../components/AppShell";
import { Alert, api } from "../../lib/api";
import { wsClient } from "../../lib/websocket";

const SEV_BADGES: Record<string, { bg: string; text: string; border: string }> = {
  CRITICAL: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
  ERROR: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200" },
  WARNING: { bg: "bg-amber-50", text: "text-amber-800", border: "border-amber-200" },
  INFO: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
};

const STATUS_BADGES: Record<string, { bg: string; text: string; border: string }> = {
  OPEN: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
  ACKNOWLEDGED: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
  SUPPRESSED: { bg: "bg-slate-100", text: "text-slate-600", border: "border-slate-200" },
  RESOLVED: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200" },
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);

  // Suppression modal
  const [suppressAlertId, setSuppressAlertId] = useState<string | null>(null);
  const [suppressReason, setSuppressReason] = useState("");
  const [suppressDuration, setSuppressDuration] = useState(60);

  const loadAlerts = async () => {
    try {
      const params: Record<string, string> = {};
      if (statusFilter !== "ALL") params.status = statusFilter;
      if (severityFilter !== "ALL") params.severity = severityFilter;

      const data = await api.listAlerts(params);
      setAlerts(data);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAlerts();
    const disconnect = wsClient.connect("dashboard", () => {
      loadAlerts();
    });
    return () => disconnect();
  }, [statusFilter, severityFilter]);

  const handleAcknowledge = async (id: string) => {
    try {
      await api.acknowledgeAlert(id);
      await loadAlerts();
    } catch (e) {}
  };

  const handleSuppress = async () => {
    if (!suppressAlertId || !suppressReason.trim()) return;
    try {
      await api.suppressAlert(suppressAlertId, suppressReason, suppressDuration);
      setSuppressAlertId(null);
      setSuppressReason("");
      await loadAlerts();
    } catch (e) {}
  };

  const handleResolve = async (id: string) => {
    try {
      await api.resolveAlert(id);
      await loadAlerts();
    } catch (e) {}
  };

  const filteredAlerts = alerts.filter(
    (a) =>
      a.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.fingerprint.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (a.service_name && a.service_name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const openCount = alerts.filter((a) => a.status === "OPEN").length;
  const suppressedCount = alerts.filter((a) => a.status === "SUPPRESSED").length;
  const resolvedCount = alerts.filter((a) => a.status === "RESOLVED").length;

  return (
    <AppShell
      title="Alert Inbox & Deduplication"
      subtitle="Fingerprint Correlated Telemetry"
      openAlertsCount={openCount}
      onIncidentCreated={loadAlerts}
    >
      <div className="space-y-6">
        {/* KPI Strip */}
        <div className="grid gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
            <span className="text-xs text-slate-500 font-medium">Total Ingested</span>
            <p className="text-2xl font-bold text-slate-900 mt-1">{alerts.length}</p>
            <p className="text-[11px] font-mono text-slate-400 mt-1">Telemetry events</p>
          </div>
          <div className="rounded-xl border border-red-200 bg-red-50/50 p-4 shadow-xs">
            <span className="text-xs text-red-700 font-medium">Open / Unacknowledged</span>
            <p className="text-2xl font-bold text-red-700 mt-1">{openCount}</p>
            <p className="text-[11px] font-mono text-red-600 mt-1">Requires triage</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 shadow-xs">
            <span className="text-xs text-amber-800 font-medium">Suppressed / Snoozed</span>
            <p className="text-2xl font-bold text-amber-800 mt-1">{suppressedCount}</p>
            <p className="text-[11px] font-mono text-amber-700 mt-1">Fingerprint silenced</p>
          </div>
          <div className="rounded-xl border border-green-200 bg-green-50/50 p-4 shadow-xs">
            <span className="text-xs text-green-800 font-medium">Resolved Alerts</span>
            <p className="text-2xl font-bold text-green-700 mt-1">{resolvedCount}</p>
            <p className="text-[11px] font-mono text-green-600 mt-1">Normal state recovered</p>
          </div>
        </div>

        {/* Filter Controls Bar */}
        <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-xs sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Filter by alert title, fingerprint hash, or service..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:border-blue-600 focus:outline-none"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Status pills */}
            <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 bg-slate-50/70">
              {["ALL", "OPEN", "ACKNOWLEDGED", "SUPPRESSED", "RESOLVED"].map((st) => (
                <button
                  key={st}
                  onClick={() => setStatusFilter(st)}
                  className={`rounded px-2.5 py-1 text-[11px] font-mono font-semibold transition-all ${
                    statusFilter === st
                      ? "bg-white text-blue-700 shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {st}
                </button>
              ))}
            </div>

            {/* Severity */}
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 focus:border-blue-600 focus:outline-none"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="ERROR">Error</option>
              <option value="WARNING">Warning</option>
              <option value="INFO">Info</option>
            </select>
          </div>
        </div>

        {/* Alert Cards List */}
        <div className="space-y-3">
          {loading ? (
            <div className="p-12 text-center text-xs text-slate-400 font-mono">
              Loading correlated alerts...
            </div>
          ) : filteredAlerts.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white p-12 text-center shadow-xs">
              <CheckCircle2 className="mx-auto h-8 w-8 text-green-600 mb-2" />
              <h4 className="text-sm font-bold text-slate-800">No Alerts Matching Filter</h4>
              <p className="text-xs text-slate-500 mt-1">All monitoring probes reporting within nominal parameters.</p>
            </div>
          ) : (
            filteredAlerts.map((al) => {
              const sev = SEV_BADGES[al.severity] || SEV_BADGES.INFO;
              const st = STATUS_BADGES[al.status] || STATUS_BADGES.OPEN;

              return (
                <div
                  key={al.id}
                  className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs hover:border-slate-300 transition-all"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1.5 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-md border px-2 py-0.5 text-[11px] font-bold font-mono ${sev.bg} ${sev.text} ${sev.border}`}>
                          {al.severity}
                        </span>

                        <span className={`rounded border px-2 py-0.5 text-[10px] font-mono font-medium ${st.bg} ${st.text} ${st.border}`}>
                          {al.status}
                        </span>

                        <span className="text-xs font-mono font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                          {al.service_name || "Infrastructure"}
                        </span>

                        <span className="text-[11px] font-mono text-slate-500 bg-blue-50 text-blue-700 px-2 py-0.5 rounded border border-blue-200">
                          Fired {al.occurrence_count} times
                        </span>
                      </div>

                      <h3 className="text-sm font-bold text-slate-900">{al.title}</h3>

                      {al.description && (
                        <p className="text-xs text-slate-600 line-clamp-2">{al.description}</p>
                      )}

                      <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400 pt-1">
                        <span>Fingerprint: <strong className="text-slate-600">{al.fingerprint}</strong></span>
                        <span>•</span>
                        <span>Source: {al.source}</span>
                        <span>•</span>
                        <span>First seen: {new Date(al.first_seen).toLocaleTimeString()}</span>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 shrink-0 self-start sm:self-auto">
                      {al.status === "OPEN" && (
                        <>
                          <button
                            onClick={() => handleAcknowledge(al.id)}
                            className="rounded-lg bg-blue-600 px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors shadow-2xs"
                          >
                            Acknowledge
                          </button>
                          <button
                            onClick={() => setSuppressAlertId(al.id)}
                            className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                          >
                            Suppress
                          </button>
                        </>
                      )}

                      {al.status !== "RESOLVED" && (
                        <button
                          onClick={() => handleResolve(al.id)}
                          className="rounded-lg border border-green-200 bg-green-50 px-2.5 py-1.5 text-xs font-semibold text-green-700 hover:bg-green-100 transition-colors"
                        >
                          Resolve
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Suppression Modal (no native prompt!) */}
      {suppressAlertId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-modal">
            <h4 className="text-base font-bold text-slate-900 mb-2">Suppress Alert Fingerprint</h4>
            <p className="text-xs text-slate-500 mb-4">
              Silences recurring notifications for this fingerprint signature during scheduled maintenance or ongoing remediation.
            </p>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Suppression Duration</label>
                <div className="grid grid-cols-4 gap-2">
                  {[
                    { label: "15m", val: 15 },
                    { label: "1h", val: 60 },
                    { label: "4h", val: 240 },
                    { label: "24h", val: 1440 },
                  ].map((d) => (
                    <button
                      key={d.val}
                      type="button"
                      onClick={() => setSuppressDuration(d.val)}
                      className={`rounded-lg border p-2 text-xs font-mono font-semibold transition-all ${
                        suppressDuration === d.val
                          ? "border-blue-600 bg-blue-50 text-blue-700 shadow-2xs"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Justification Reason <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={3}
                  required
                  placeholder="e.g. Known upstream third-party degradation; maintenance window open..."
                  value={suppressReason}
                  onChange={(e) => setSuppressReason(e.target.value)}
                  className="form-input resize-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setSuppressAlertId(null)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSuppress}
                  className="rounded-lg bg-amber-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-amber-700"
                >
                  Confirm Suppression
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
