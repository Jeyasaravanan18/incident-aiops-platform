"use client";

import React, { useEffect, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Filter,
  Lock,
  RefreshCw,
  ScrollText,
  Search,
  ShieldCheck,
} from "lucide-react";

import AppShell from "../../components/AppShell";
import { api, LogEntry, Service } from "../../lib/api";

const LEVEL_COLORS: Record<string, { badge: string; text: string }> = {
  CRITICAL: { badge: "bg-red-100 border-red-200 text-red-800", text: "text-red-900 font-bold" },
  ERROR: { badge: "bg-red-50 border-red-200 text-red-700", text: "text-red-800 font-semibold" },
  WARN: { badge: "bg-amber-50 border-amber-200 text-amber-800", text: "text-amber-900 font-medium" },
  WARNING: { badge: "bg-amber-50 border-amber-200 text-amber-800", text: "text-amber-900 font-medium" },
  INFO: { badge: "bg-blue-50 border-blue-200 text-blue-700", text: "text-slate-800" },
  DEBUG: { badge: "bg-slate-100 border-slate-200 text-slate-600", text: "text-slate-600" },
};

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [serviceFilter, setServiceFilter] = useState("");
  const [levelFilter, setLevelFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const loadLogs = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (serviceFilter) params.service = serviceFilter;
      if (levelFilter) params.level = levelFilter;
      if (searchQuery) params.search = searchQuery;
      params.limit = "50";

      const [logData, srvData] = await Promise.all([
        api.listLogs(params),
        api.listServices(),
      ]);
      setLogs(logData);
      setServices(srvData);
    } catch (e) {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, [serviceFilter, levelFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadLogs();
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <AppShell
      title="Structured Log Explorer"
      subtitle="Redacted Telemetry & Trace Correlation"
    >
      <div className="space-y-6">
        {/* Search & Filter Bar */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
          <form onSubmit={handleSearchSubmit} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Filter logs by keyword, exception signature, or path... (e.g. 500, timeout, token)"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-2 text-xs text-slate-900 placeholder-slate-400 focus:border-blue-600 focus:outline-none"
              />
            </div>
            <button
              type="submit"
              className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-bold text-white hover:bg-blue-700 transition-colors shadow-2xs"
            >
              Search Logs
            </button>
          </form>

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-100 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={serviceFilter}
                onChange={(e) => setServiceFilter(e.target.value)}
                className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 focus:border-blue-600 focus:outline-none"
              >
                <option value="">All Services ({services.length})</option>
                {services.map((s) => (
                  <option key={s.id} value={s.slug}>
                    {s.name}
                  </option>
                ))}
              </select>

              {/* Log Level Pills */}
              <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-0.5 bg-slate-50">
                {["", "ERROR", "WARN", "INFO", "DEBUG"].map((lvl) => (
                  <button
                    key={lvl}
                    onClick={() => setLevelFilter(lvl)}
                    className={`rounded px-2.5 py-1 text-[11px] font-mono font-semibold transition-all ${
                      levelFilter === lvl
                        ? "bg-white text-blue-700 shadow-2xs"
                        : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {lvl || "ALL"}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center gap-2 text-slate-500 font-mono text-[11px]">
              <span className="flex items-center gap-1 text-green-700 font-semibold">
                <ShieldCheck className="h-3.5 w-3.5" /> PII & Auth Token Redaction Active
              </span>
              <span>•</span>
              <span>Limit: 50 records</span>
            </div>
          </div>
        </div>

        {/* High-density Log Stream */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-xs overflow-hidden">
          <div className="bg-slate-50/80 px-4 py-2.5 border-b border-slate-200 flex items-center justify-between text-[11px] font-mono text-slate-500 font-semibold">
            <span>TIMESTAMP / SERVICE / LEVEL / MESSAGE</span>
            <span>{logs.length} Matching Events</span>
          </div>

          {loading ? (
            <div className="p-12 text-center text-xs font-mono text-slate-400">
              Querying distributed telemetry logs...
            </div>
          ) : logs.length === 0 ? (
            <div className="p-12 text-center text-xs text-slate-500 font-mono">
              No log entries match the specified query parameters.
            </div>
          ) : (
            <div className="divide-y divide-slate-100 font-mono text-xs">
              {logs.map((log) => {
                const conf = LEVEL_COLORS[log.level] || LEVEL_COLORS.INFO;
                const isExpanded = expandedLogId === log.id;
                const isCopied = copiedId === log.id;

                return (
                  <div
                    key={log.id}
                    className="p-3 hover:bg-slate-50/80 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-2.5 min-w-0 flex-1">
                        <button
                          onClick={() => setExpandedLogId(isExpanded ? null : log.id)}
                          className="text-slate-400 hover:text-slate-600 mt-0.5"
                        >
                          {isExpanded ? (
                            <ChevronDown className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronRight className="h-3.5 w-3.5" />
                          )}
                        </button>

                        <span className="text-[11px] text-slate-400 whitespace-nowrap shrink-0 mt-0.5">
                          {new Date(log.timestamp).toLocaleTimeString([], { hour12: false, fractionalSecondDigits: 3 })}
                        </span>

                        <span className={`rounded border px-1.5 py-0.2 text-[10px] font-bold shrink-0 ${conf.badge}`}>
                          {log.level}
                        </span>

                        <span className="rounded bg-slate-100 px-1.5 py-0.2 text-[10px] text-slate-700 font-semibold shrink-0">
                          {log.service_name}
                        </span>

                        <p className={`text-xs ${conf.text} break-all`}>
                          {log.message}
                        </p>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {log.trace_id && (
                          <span className="text-[10px] text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded border border-blue-200">
                            trace: {log.trace_id.slice(0, 8)}
                          </span>
                        )}

                        <button
                          onClick={() => copyToClipboard(JSON.stringify(log, null, 2), log.id)}
                          title="Copy log entry as JSON"
                          className="rounded p-1 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700 transition-colors"
                        >
                          {isCopied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </div>

                    {/* Expandable JSON detail */}
                    {isExpanded && (
                      <div className="mt-3 ml-6 rounded-lg border border-slate-200 bg-slate-50 p-3 text-[11px] font-mono text-slate-800 overflow-x-auto">
                        <div className="flex items-center justify-between mb-2 text-slate-500 text-[10px]">
                          <span>CORRELATED PAYLOAD & METADATA</span>
                          <span>ID: {log.id}</span>
                        </div>
                        <pre className="text-slate-700 whitespace-pre-wrap">
                          {JSON.stringify(log.metadata_json || {}, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
