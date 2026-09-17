"use client";

import React, { use, useEffect, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  AlertOctagon,
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileText,
  Flame,
  MessageSquare,
  Play,
  RotateCcw,
  ScrollText,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  UserPlus,
  X,
} from "lucide-react";

import AppShell from "../../../components/AppShell";
import {
  AIAnalysis,
  Alert,
  api,
  Incident,
  IncidentComment,
  LogEntry,
  Postmortem,
  Runbook,
  TimelineEvent,
  User,
} from "../../../lib/api";
import { wsClient } from "../../../lib/websocket";

const SEV_BADGES: Record<string, { bg: string; text: string; border: string }> = {
  SEV1: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
  SEV2: { bg: "bg-orange-50", text: "text-orange-800", border: "border-orange-200" },
  SEV3: { bg: "bg-amber-50", text: "text-amber-800", border: "border-amber-200" },
  SEV4: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
};

const PIPELINE_STAGES = [
  "DETECTED",
  "TRIGGERED",
  "ACKNOWLEDGED",
  "INVESTIGATING",
  "MITIGATING",
  "RESOLVED",
  "CLOSED",
];

export default function IncidentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const incidentId = resolvedParams.id;

  const [incident, setIncident] = useState<Incident | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [comments, setComments] = useState<IncidentComment[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);
  const [analysis, setAnalysis] = useState<AIAnalysis | null>(null);
  const [postmortem, setPostmortem] = useState<Postmortem | null>(null);
  const [users, setUsers] = useState<User[]>([]);

  const [activeTab, setActiveTab] = useState<"timeline" | "ai" | "alerts" | "logs" | "runbook" | "postmortem" | "comments">("timeline");
  const [newComment, setNewComment] = useState("");
  const [submittingComment, setSubmittingComment] = useState(false);
  const [runningAnalysis, setRunningAnalysis] = useState(false);
  const [generatingPostmortem, setGeneratingPostmortem] = useState(false);
  const [reopenReason, setReopenReason] = useState("");
  const [showReopenModal, setShowReopenModal] = useState(false);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [selectedAssignee, setSelectedAssignee] = useState("");
  const [assignReason, setAssignReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const loadAll = async () => {
    try {
      const [inc, tm, al, pm, an, us] = await Promise.all([
        api.getIncident(incidentId),
        api.getIncidentTimeline(incidentId),
        api.getIncidentAlerts(incidentId),
        api.getPostmortemByIncident(incidentId),
        api.getIncidentAnalysis(incidentId),
        api.listUsers(),
      ]);

      setIncident(inc);
      setTimeline(tm);
      setAlerts(al);
      setPostmortem(pm);
      setAnalysis(an);
      setUsers(us);

      if (inc.service_id) {
        api.listLogs({ service: inc.service_name || "", limit: "25" }).then(setLogs).catch(() => {});
        api.listRunbooks(inc.service_id).then(setRunbooks).catch(() => {});
      }
    } catch (e: any) {
      setActionError(e.message || "Failed to load incident");
    }
  };

  useEffect(() => {
    loadAll();

    const disconnect = wsClient.connect(`incident:${incidentId}`, () => {
      loadAll();
    });

    return () => disconnect();
  }, [incidentId]);

  // Outage elapsed timer
  useEffect(() => {
    if (!incident) return;
    const start = new Date(incident.detected_at || incident.created_at).getTime();
    const updateTimer = () => {
      const end = incident.resolved_at ? new Date(incident.resolved_at).getTime() : Date.now();
      setElapsedSeconds(Math.max(0, Math.floor((end - start) / 1000)));
    };
    updateTimer();
    const interval = setInterval(updateTimer, 1000);
    return () => clearInterval(interval);
  }, [incident]);

  const formatElapsed = (sec: number) => {
    const hours = Math.floor(sec / 3600);
    const mins = Math.floor((sec % 3600) / 60);
    const seconds = sec % 60;
    if (hours > 0) return `${hours}h ${mins}m ${seconds}s`;
    return `${mins}m ${seconds}s`;
  };

  const handleTransition = async (targetStatus: string) => {
    setActionError(null);
    try {
      await api.transitionIncident(incidentId, targetStatus);
      await loadAll();
    } catch (err: any) {
      setActionError(err.message || "Failed state transition");
    }
  };

  const handleReopen = async () => {
    if (!reopenReason.trim()) return;
    setActionError(null);
    try {
      await api.reopenIncident(incidentId, reopenReason);
      setShowReopenModal(false);
      setReopenReason("");
      await loadAll();
    } catch (err: any) {
      setActionError(err.message || "Failed to reopen incident");
    }
  };

  const handleAssign = async () => {
    if (!selectedAssignee) return;
    setActionError(null);
    try {
      await api.assignIncident(incidentId, selectedAssignee, assignReason);
      setShowAssignModal(false);
      setAssignReason("");
      await loadAll();
    } catch (err: any) {
      setActionError(err.message || "Failed to assign incident");
    }
  };

  const handleAddComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim()) return;
    setSubmittingComment(true);
    try {
      await api.addComment(incidentId, newComment);
      setNewComment("");
      await loadAll();
    } catch (err: any) {
      setActionError(err.message || "Failed to add comment");
    } finally {
      setSubmittingComment(false);
    }
  };

  const handleRunAnalysis = async () => {
    setRunningAnalysis(true);
    try {
      const res = await api.analyzeIncident(incidentId);
      setAnalysis(res);
      setActiveTab("ai");
      await loadAll();
    } catch (err: any) {
      setActionError(err.message || "Failed to trigger AI analysis");
    } finally {
      setRunningAnalysis(false);
    }
  };

  const handleDraftPostmortem = async () => {
    setGeneratingPostmortem(true);
    try {
      const draft = await api.generatePostmortemDraft(incidentId);
      const created = await api.createPostmortem(draft);
      setPostmortem(created);
      setActiveTab("postmortem");
      await loadAll();
    } catch (err: any) {
      setActionError(err.message || "Failed to draft postmortem");
    } finally {
      setGeneratingPostmortem(false);
    }
  };

  if (!incident) {
    return (
      <AppShell title="Incident Command" subtitle="Loading...">
        <div className="flex items-center justify-center py-20 font-mono text-xs text-slate-500">
          Loading SRE incident command center...
        </div>
      </AppShell>
    );
  }

  const sev = SEV_BADGES[incident.severity] || SEV_BADGES.SEV3;
  const currentStageIndex = PIPELINE_STAGES.indexOf(incident.status);

  return (
    <AppShell
      breadcrumbs={[
        { label: "Incidents", href: "/incidents" },
        { label: `INC-${incident.id.slice(0, 8).toUpperCase()}` },
      ]}
      onIncidentCreated={loadAll}
    >
      <div className="space-y-6">
        {actionError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs text-red-700 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{actionError}</span>
            </div>
            <button onClick={() => setActionError(null)} className="text-red-500 hover:text-red-800">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {/* Top Incident Banner & Command Card */}
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2.5 max-w-3xl">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-0.5 text-xs font-bold font-mono ${sev.bg} ${sev.text} ${sev.border}`}>
                  {incident.severity === "SEV1" && (
                    <span className="h-1.5 w-1.5 rounded-full bg-red-600 animate-pulse-slow"></span>
                  )}
                  {incident.severity}
                </span>

                <span className="rounded-md border border-slate-200 bg-slate-100 px-2.5 py-0.5 text-xs font-mono font-semibold text-slate-700">
                  {incident.status}
                </span>

                <span className="font-semibold text-blue-600 text-xs bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
                  {incident.service_name || "Platform Service"}
                </span>

                {incident.resolved_at ? (
                  <span className="text-xs font-mono text-green-700 bg-green-50 px-2 py-0.5 rounded border border-green-200 flex items-center gap-1 font-semibold">
                    <CheckCircle2 className="h-3 w-3" /> Resolved in {formatElapsed(elapsedSeconds)}
                  </span>
                ) : (
                  <span className="text-xs font-mono text-red-700 bg-red-50 px-2 py-0.5 rounded border border-red-200 flex items-center gap-1 font-bold">
                    <Clock className="h-3 w-3 animate-spin" /> Outage Duration: {formatElapsed(elapsedSeconds)}
                  </span>
                )}
              </div>

              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 leading-tight">
                {incident.title}
              </h1>

              <p className="text-xs text-slate-600 leading-relaxed">
                {incident.description || "No description documented at incident declaration."}
              </p>
            </div>

            {/* Responder & On-Call Commander Pill */}
            <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50/80 p-3.5 shrink-0 self-start">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-blue-700 font-bold font-mono text-sm shrink-0">
                {incident.assignee_name ? incident.assignee_name[0] : "?"}
              </div>
              <div>
                <p className="text-[10px] font-mono uppercase text-slate-500 font-medium">Incident Commander</p>
                <p className="text-xs font-bold text-slate-800">
                  {incident.assignee_name || "Unassigned"}
                </p>
                <button
                  onClick={() => setShowAssignModal(true)}
                  className="flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:text-blue-800 hover:underline mt-0.5"
                >
                  <UserPlus className="h-3 w-3" /> Reassign / Escalate
                </button>
              </div>
            </div>
          </div>

          {/* SRE State Machine Stepper */}
          <div className="mt-6 pt-5 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-mono text-slate-500 font-medium">Lifecycle Progression</span>
              <span className="text-xs font-mono font-bold text-slate-700">Stage {currentStageIndex + 1} of {PIPELINE_STAGES.length}</span>
            </div>

            <div className="grid grid-cols-7 gap-1 sm:gap-2">
              {PIPELINE_STAGES.map((stage, idx) => {
                const isCurrent = stage === incident.status;
                const isPassed = idx < currentStageIndex;

                return (
                  <div key={stage} className="text-center">
                    <div
                      className={`h-2 rounded-full transition-all ${
                        isCurrent
                          ? "bg-blue-600 shadow-xs"
                          : isPassed
                          ? "bg-green-500"
                          : "bg-slate-200"
                      }`}
                    />
                    <p
                      className={`mt-1.5 text-[9px] sm:text-[10px] font-mono truncate uppercase ${
                        isCurrent
                          ? "font-bold text-blue-700"
                          : isPassed
                          ? "font-medium text-green-700"
                          : "text-slate-400"
                      }`}
                    >
                      {stage}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Fast Transition Action Bar */}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-100 bg-slate-50/50 -mx-6 -mb-6 p-4 rounded-b-xl">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-slate-700 mr-1">Lifecycle Action:</span>

              {incident.status === "DETECTED" && (
                <>
                  <button
                    onClick={() => handleTransition("TRIGGERED")}
                    className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 transition-colors shadow-2xs"
                  >
                    Trigger Pager Escalation
                  </button>
                  <button
                    onClick={() => handleTransition("ACKNOWLEDGED")}
                    className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors shadow-2xs"
                  >
                    Acknowledge Directly
                  </button>
                </>
              )}

              {incident.status === "TRIGGERED" && (
                <>
                  <button
                    onClick={() => handleTransition("ACKNOWLEDGED")}
                    className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors shadow-2xs"
                  >
                    Acknowledge Page
                  </button>
                  <button
                    onClick={() => handleTransition("INVESTIGATING")}
                    className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 transition-colors shadow-2xs"
                  >
                    Start Investigating
                  </button>
                </>
              )}

              {incident.status === "ACKNOWLEDGED" && (
                <>
                  <button
                    onClick={() => handleTransition("INVESTIGATING")}
                    className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 transition-colors shadow-2xs"
                  >
                    Start Investigation
                  </button>
                  <button
                    onClick={() => handleTransition("MITIGATING")}
                    className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 transition-colors shadow-2xs"
                  >
                    Begin Mitigating
                  </button>
                </>
              )}

              {incident.status === "INVESTIGATING" && (
                <>
                  <button
                    onClick={() => handleTransition("MITIGATING")}
                    className="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 transition-colors shadow-2xs"
                  >
                    Begin Mitigating
                  </button>
                  <button
                    onClick={() => handleTransition("RESOLVED")}
                    className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 transition-colors shadow-2xs"
                  >
                    Mark Resolved
                  </button>
                </>
              )}

              {incident.status === "MITIGATING" && (
                <button
                  onClick={() => handleTransition("RESOLVED")}
                  className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 transition-colors shadow-2xs"
                >
                  Mark Resolved
                </button>
              )}

              {incident.status === "RESOLVED" && (
                <>
                  <button
                    onClick={() => handleTransition("CLOSED")}
                    className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-900 transition-colors shadow-2xs"
                  >
                    Close Incident
                  </button>
                  <button
                    onClick={() => setShowReopenModal(true)}
                    className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 transition-colors shadow-2xs"
                  >
                    Reopen Incident
                  </button>
                </>
              )}

              {incident.status === "CLOSED" && (
                <button
                  onClick={() => setShowReopenModal(true)}
                  className="rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-100 transition-colors shadow-2xs"
                >
                  Reopen Closed Incident
                </button>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleRunAnalysis}
                disabled={runningAnalysis}
                className="flex items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 shadow-2xs transition-colors"
              >
                <Sparkles className="h-3.5 w-3.5 text-blue-600" />
                {runningAnalysis ? "Analyzing Telemetry..." : "Run AI Root Cause Analysis"}
              </button>
            </div>
          </div>
        </div>

        {/* 7 Tab Navigation Bar */}
        <div className="flex border-b border-slate-200 overflow-x-auto">
          {[
            { id: "timeline", label: "Timeline & Audit", icon: Clock, count: timeline.length },
            { id: "ai", label: "AI Copilot & RCA", icon: Bot, highlight: !!analysis },
            { id: "alerts", label: "Correlated Alerts", icon: ShieldAlert, count: alerts.length },
            { id: "logs", label: "Redacted Logs", icon: ScrollText, count: logs.length },
            { id: "runbook", label: "Runbooks", icon: FileText, count: runbooks.length },
            { id: "postmortem", label: "Postmortem", icon: FileText, highlight: !!postmortem },
            { id: "comments", label: "War Room Comms", icon: MessageSquare, count: comments.length },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-semibold whitespace-nowrap transition-colors ${
                  isActive
                    ? "border-blue-600 text-blue-700 bg-blue-50/50"
                    : "border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900"
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? "text-blue-600" : "text-slate-400"}`} />
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] font-mono ${
                      isActive ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
                {tab.highlight && !tab.count && (
                  <span className="h-1.5 w-1.5 rounded-full bg-green-500"></span>
                )}
              </button>
            );
          })}
        </div>

        {/* Tab 1: Timeline */}
        {activeTab === "timeline" && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-4">Immutable Audit Timeline</h3>
            {timeline.length === 0 ? (
              <p className="text-xs text-slate-500 font-mono py-8 text-center">No timeline events recorded yet.</p>
            ) : (
              <div className="relative pl-6 space-y-6 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
                {timeline.map((event) => (
                  <div key={event.id} className="relative group">
                    <div className="absolute -left-6 top-1 h-3 w-3 rounded-full border-2 border-white bg-blue-600 shadow-2xs"></div>
                    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3 hover:bg-slate-50 transition-colors">
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span className="text-xs font-bold text-slate-800">{event.event_type}</span>
                        <span className="text-[11px] font-mono text-slate-400">
                          {new Date(event.created_at).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-xs text-slate-600">{event.message}</p>
                      {event.actor_name && (
                        <p className="mt-1 text-[10px] font-mono text-slate-400">By: {event.actor_name}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 2: AI RCA */}
        {activeTab === "ai" && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs space-y-6">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
                  <Sparkles className="h-4.5 w-4.5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">AIOps Root Cause Intelligence</h3>
                  <p className="text-xs text-slate-500">Autonomous telemetry correlation & mitigation plan</p>
                </div>
              </div>
              <button
                onClick={handleRunAnalysis}
                disabled={runningAnalysis}
                className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors shadow-2xs"
              >
                {runningAnalysis ? "Analyzing..." : "Re-Analyze"}
              </button>
            </div>

            {analysis ? (
              <div className="space-y-4">
                <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-blue-900 uppercase font-mono">Executive Summary</span>
                    <span className="text-xs font-mono font-bold text-green-700 bg-green-50 px-2 py-0.5 rounded border border-green-200">
                      Confidence: {Math.round(analysis.confidence * 100)}%
                    </span>
                  </div>
                  <p className="text-xs text-slate-700 leading-relaxed">{analysis.summary}</p>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <h4 className="text-xs font-bold text-slate-900 mb-2 uppercase font-mono">Probable Root Causes</h4>
                    <ul className="space-y-1.5 text-xs text-slate-700 list-disc pl-4">
                      {analysis.probable_causes.map((c, i) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <h4 className="text-xs font-bold text-slate-900 mb-2 uppercase font-mono">Recommended Actions</h4>
                    <ul className="space-y-1.5 text-xs text-slate-700 list-disc pl-4">
                      {analysis.recommended_actions.map((a, i) => (
                        <li key={i}>{a}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-12 text-center">
                <Bot className="h-10 w-10 text-slate-300 mx-auto mb-2" />
                <p className="text-xs text-slate-500">No AI analysis executed for this incident yet.</p>
                <button
                  onClick={handleRunAnalysis}
                  className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 transition-colors"
                >
                  Run Telemetry Correlation
                </button>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Correlated Alerts */}
        {activeTab === "alerts" && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-4">Correlated Fingerprint Telemetry</h3>
            {alerts.length === 0 ? (
              <p className="text-xs text-slate-500 py-8 text-center font-mono">No alerts mapped to this incident.</p>
            ) : (
              <div className="divide-y divide-slate-100 overflow-x-auto">
                {alerts.map((al) => (
                  <div key={al.id} className="py-3 flex items-center justify-between gap-4 hover:bg-slate-50 px-2 rounded-lg">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="rounded border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-bold font-mono text-red-700">
                          {al.severity}
                        </span>
                        <h4 className="text-xs font-bold text-slate-900">{al.title}</h4>
                      </div>
                      <p className="text-[11px] font-mono text-slate-500">
                        Fingerprint: {al.fingerprint} • Occurrences: {al.occurrence_count}
                      </p>
                    </div>
                    <span className="text-xs font-mono font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                      {al.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 4: Logs */}
        {activeTab === "logs" && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-4">Correlated System Logs</h3>
            {logs.length === 0 ? (
              <p className="text-xs text-slate-500 py-8 text-center font-mono">No error logs captured during outage window.</p>
            ) : (
              <div className="space-y-1.5 font-mono text-xs max-h-96 overflow-y-auto">
                {logs.map((lg) => (
                  <div key={lg.id} className="rounded border border-slate-100 bg-slate-50 p-2.5 flex items-start gap-2.5">
                    <span className="text-[10px] text-slate-400 shrink-0">
                      {new Date(lg.timestamp).toLocaleTimeString()}
                    </span>
                    <span className={`px-1 rounded text-[10px] font-bold shrink-0 ${
                      lg.level === "ERROR" ? "bg-red-100 text-red-700" : "bg-blue-100 text-blue-700"
                    }`}>
                      {lg.level}
                    </span>
                    <span className="text-slate-800 break-all">{lg.message}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 5: Runbooks */}
        {activeTab === "runbook" && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-4">SRE Operational Runbooks</h3>
            {runbooks.length === 0 ? (
              <p className="text-xs text-slate-500 py-8 text-center font-mono">No runbooks linked to this service type.</p>
            ) : (
              <div className="space-y-4">
                {runbooks.map((rb) => (
                  <div key={rb.id} className="rounded-xl border border-slate-200 p-4 bg-slate-50/50">
                    <h4 className="text-sm font-bold text-slate-900 mb-1">{rb.title}</h4>
                    <p className="text-xs font-mono text-slate-500 mb-3">Type: {rb.incident_type}</p>
                    <pre className="text-xs font-mono bg-white p-3 rounded-lg border border-slate-200 whitespace-pre-wrap text-slate-800">
                      {rb.body}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Tab 6: Postmortem */}
        {activeTab === "postmortem" && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900">Blameless Postmortem Studio</h3>
              <button
                onClick={handleDraftPostmortem}
                disabled={generatingPostmortem}
                className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 transition-colors shadow-2xs"
              >
                {generatingPostmortem ? "Drafting..." : "Generate AI Postmortem"}
              </button>
            </div>

            {postmortem ? (
              <div className="space-y-4 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Status: <strong className="text-slate-800">{postmortem.status}</strong></span>
                  <Link href="/postmortems" className="text-blue-600 hover:underline">
                    View in Postmortem Manager &rarr;
                  </Link>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <h5 className="font-bold text-slate-900 mb-1">Executive Summary</h5>
                  <p className="text-slate-700">{postmortem.summary}</p>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <h5 className="font-bold text-slate-900 mb-1">Root Cause Analysis</h5>
                  <p className="text-slate-700">{postmortem.root_cause || "Pending Investigation"}</p>
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-slate-500">
                No postmortem created for this incident yet. Click "Generate AI Postmortem" to build the draft.
              </div>
            )}
          </div>
        )}

        {/* Tab 7: War Room Comms */}
        {activeTab === "comments" && (
          <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Commander Communications Log</h3>
            <form onSubmit={handleAddComment} className="flex gap-2">
              <input
                type="text"
                placeholder="Post update to war room channel..."
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                className="form-input flex-1"
              />
              <button
                type="submit"
                disabled={submittingComment}
                className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-2xs"
              >
                <Send className="h-3.5 w-3.5" />
                Send
              </button>
            </form>
          </div>
        )}
      </div>

      {/* Assign Commander Modal */}
      {showAssignModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-modal">
            <h4 className="text-base font-bold text-slate-900 mb-3">Assign Incident Commander</h4>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Select SRE Responder</label>
                <select
                  value={selectedAssignee}
                  onChange={(e) => setSelectedAssignee(e.target.value)}
                  className="form-input cursor-pointer"
                >
                  <option value="">Select Responder...</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.full_name} ({u.role})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Escalation Reason</label>
                <input
                  type="text"
                  placeholder="e.g. Primary on-call handoff"
                  value={assignReason}
                  onChange={(e) => setAssignReason(e.target.value)}
                  className="form-input"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowAssignModal(false)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAssign}
                  className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
                >
                  Confirm Assignment
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Reopen Incident Modal */}
      {showReopenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-modal">
            <h4 className="text-base font-bold text-red-700 mb-2">Reopen Incident</h4>
            <p className="text-xs text-slate-500 mb-4">
              Provide justification for reopening this incident (e.g. regression detected, symptoms recurred).
            </p>
            <div className="space-y-3">
              <textarea
                rows={3}
                required
                placeholder="Reason for reopening..."
                value={reopenReason}
                onChange={(e) => setReopenReason(e.target.value)}
                className="form-input resize-none"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowReopenModal(false)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleReopen}
                  className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
                >
                  Reopen Incident
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
