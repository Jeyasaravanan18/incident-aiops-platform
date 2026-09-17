"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  Download,
  FileCheck,
  FileEdit,
  FileText,
  Filter,
  Search,
  ShieldCheck,
} from "lucide-react";

import AppShell from "../../components/AppShell";
import { api, Postmortem } from "../../lib/api";
import { useToast } from "../../components/Toast";

const STATUS_BADGES: Record<string, { badge: string; text: string }> = {
  DRAFT: { badge: "bg-slate-100 text-slate-700 border-slate-200", text: "Draft" },
  REVIEW: { badge: "bg-amber-50 text-amber-800 border-amber-200", text: "In Review" },
  APPROVED: { badge: "bg-green-50 text-green-700 border-green-200", text: "Approved / Closed" },
};

export default function PostmortemsPage() {
  const { toast } = useToast();
  const [postmortems, setPostmortems] = useState<Postmortem[]>([]);
  const [selectedPostmortem, setSelectedPostmortem] = useState<Postmortem | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    fetchPostmortems();
  }, []);

  const fetchPostmortems = async () => {
    try {
      setLoading(true);
      const list = await api.listPostmortems();
      setPostmortems(list);
      if (list.length > 0 && !selectedPostmortem) {
        setSelectedPostmortem(list[0]);
      } else if (list.length > 0 && selectedPostmortem) {
        const found = list.find((p) => p.id === selectedPostmortem.id);
        setSelectedPostmortem(found || list[0]);
      }
    } catch (e) {
      console.error("Failed to fetch postmortems", e);
    } finally {
      setLoading(false);
    }
  };

  const filteredPostmortems = postmortems.filter((pm) => {
    const matchesStatus = statusFilter === "ALL" || pm.status === statusFilter;
    const matchesSearch =
      pm.summary.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (pm.incident_title && pm.incident_title.toLowerCase().includes(searchQuery.toLowerCase())) ||
      (pm.root_cause && pm.root_cause.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesStatus && matchesSearch;
  });

  const handleStatusUpdate = async (newStatus: "DRAFT" | "REVIEW" | "APPROVED") => {
    if (!selectedPostmortem) return;
    try {
      setUpdating(true);
      const updated = await api.updatePostmortem(selectedPostmortem.id, { status: newStatus });
      setSelectedPostmortem(updated);
      toast.success(`Postmortem status updated to ${newStatus}`, "Status Updated");
      await fetchPostmortems();
    } catch (e: any) {
      toast.error(e.message || "Failed to update status", "Error");
    } finally {
      setUpdating(false);
    }
  };

  const copyMarkdown = () => {
    if (!selectedPostmortem) return;
    const md = `# Blameless Postmortem: ${selectedPostmortem.incident_title || "Incident Report"}
Status: ${selectedPostmortem.status}
Date: ${new Date(selectedPostmortem.created_at).toLocaleDateString()}

## Executive Summary
${selectedPostmortem.summary}

## Impact Assessment
${selectedPostmortem.impact}

## Timeline of Events
${selectedPostmortem.timeline}

## Root Cause Analysis
${selectedPostmortem.root_cause || "Pending Investigation"}

## Contributing Factors
${selectedPostmortem.contributing_factors || "None documented"}

## Remediation & Preventive Action Items
${selectedPostmortem.preventive_actions || "None documented"}

## Lessons Learned
${selectedPostmortem.lessons_learned || "None documented"}
`;

    navigator.clipboard.writeText(md);
    setCopied(true);
    toast.success("Markdown copied to clipboard!", "Copied");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <AppShell
      title="Blameless Postmortems"
      subtitle="Incident Learning & Continuous Improvement"
    >
      <div className="space-y-6">
        {/* Status Filter Tabs */}
        <div className="flex flex-wrap items-center gap-1.5 border-b border-slate-200 pb-3">
          {["ALL", "DRAFT", "REVIEW", "APPROVED"].map((tab) => (
            <button
              key={tab}
              onClick={() => setStatusFilter(tab)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                statusFilter === tab
                  ? "bg-blue-50 text-blue-700 border border-blue-200"
                  : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              {tab === "ALL" ? "All Postmortems" : tab} ({
                tab === "ALL"
                  ? postmortems.length
                  : postmortems.filter((p) => p.status === tab).length
              })
            </button>
          ))}
        </div>

        {/* 2-Column Split Workspace */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left Column: Postmortems List */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search postmortems..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:border-blue-600 focus:outline-none"
              />
            </div>

            <div className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto">
              {filteredPostmortems.length === 0 ? (
                <p className="p-4 text-center text-xs text-slate-400 font-mono">No postmortems found.</p>
              ) : (
                filteredPostmortems.map((pm) => {
                  const isSelected = selectedPostmortem?.id === pm.id;
                  const st = STATUS_BADGES[pm.status] || STATUS_BADGES.DRAFT;

                  return (
                    <button
                      key={pm.id}
                      onClick={() => setSelectedPostmortem(pm)}
                      className={`w-full text-left p-3 rounded-lg transition-colors block ${
                        isSelected
                          ? "bg-blue-50/80 border-l-3 border-blue-600 pl-2.5"
                          : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className={`rounded border px-1.5 py-0.2 text-[10px] font-mono font-semibold ${st.badge}`}>
                          {st.text}
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          {new Date(pm.created_at).toLocaleDateString()}
                        </span>
                      </div>
                      <h4 className="text-xs font-bold text-slate-900 line-clamp-1">
                        {pm.incident_title || "Incident Report"}
                      </h4>
                      <p className="text-[11px] text-slate-500 line-clamp-2 mt-0.5">
                        {pm.summary}
                      </p>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Postmortem Document Viewer */}
          <div className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            {selectedPostmortem ? (
              <div className="space-y-6">
                {/* Header & Status Workflow Bar */}
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 border-b border-slate-100 pb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`rounded border px-2 py-0.5 text-xs font-mono font-bold ${
                        STATUS_BADGES[selectedPostmortem.status]?.badge
                      }`}>
                        {selectedPostmortem.status}
                      </span>
                      <span className="text-xs font-mono text-slate-400">
                        Incident: {selectedPostmortem.incident_id.slice(0, 8)}
                      </span>
                    </div>
                    <h2 className="text-xl font-bold text-slate-900">
                      {selectedPostmortem.incident_title || "Blameless Postmortem Report"}
                    </h2>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Status transition buttons */}
                    {selectedPostmortem.status === "DRAFT" && (
                      <button
                        onClick={() => handleStatusUpdate("REVIEW")}
                        disabled={updating}
                        className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 shadow-2xs transition-colors"
                      >
                        Submit for Review
                      </button>
                    )}

                    {selectedPostmortem.status === "REVIEW" && (
                      <button
                        onClick={() => handleStatusUpdate("APPROVED")}
                        disabled={updating}
                        className="rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-green-700 shadow-2xs transition-colors"
                      >
                        Approve & Publish
                      </button>
                    )}

                    <button
                      onClick={copyMarkdown}
                      className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 shadow-2xs transition-colors"
                    >
                      {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied ? "Copied" : "Copy Markdown"}
                    </button>
                  </div>
                </div>

                {/* Structured Sections */}
                <div className="space-y-4 text-xs leading-relaxed">
                  <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
                    <h3 className="font-bold text-slate-900 text-sm mb-1.5">Executive Summary</h3>
                    <p className="text-slate-700">{selectedPostmortem.summary}</p>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <h3 className="font-bold text-slate-900 text-sm mb-1.5">Customer & Operational Impact</h3>
                    <p className="text-slate-700">{selectedPostmortem.impact}</p>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <h3 className="font-bold text-slate-900 text-sm mb-1.5">Timeline of Events</h3>
                    <p className="text-slate-700 font-mono text-[11px] whitespace-pre-wrap">{selectedPostmortem.timeline}</p>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <h3 className="font-bold text-slate-900 text-sm mb-1.5">5-Whys Root Cause Analysis</h3>
                    <p className="text-slate-700">{selectedPostmortem.root_cause || "Under Root Cause Investigation"}</p>
                  </div>

                  {selectedPostmortem.preventive_actions && (
                    <div className="rounded-xl border border-green-200 bg-green-50/40 p-4">
                      <h3 className="font-bold text-green-950 text-sm mb-1.5">Preventive Actions & Action Items</h3>
                      <p className="text-green-900 whitespace-pre-wrap">{selectedPostmortem.preventive_actions}</p>
                    </div>
                  )}

                  {selectedPostmortem.lessons_learned && (
                    <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-4">
                      <h3 className="font-bold text-blue-950 text-sm mb-1.5">Key Lessons Learned</h3>
                      <p className="text-blue-900 whitespace-pre-wrap">{selectedPostmortem.lessons_learned}</p>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="py-20 text-center text-xs text-slate-500 font-mono">
                Select a postmortem from the left column to view the full report.
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
