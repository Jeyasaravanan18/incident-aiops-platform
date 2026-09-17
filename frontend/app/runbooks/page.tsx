"use client";

import React, { useEffect, useState } from "react";
import {
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  Copy,
  ExternalLink,
  FileCode,
  Filter,
  Layers,
  Plus,
  Search,
  Terminal,
  X,
} from "lucide-react";

import AppShell from "../../components/AppShell";
import { api, Runbook, Service } from "../../lib/api";
import { useToast } from "../../components/Toast";

export default function RunbooksPage() {
  const { toast } = useToast();
  const [runbooks, setRunbooks] = useState<Runbook[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [selectedRunbook, setSelectedRunbook] = useState<Runbook | null>(null);
  const [selectedService, setSelectedService] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [copiedStep, setCopiedStep] = useState<number | null>(null);

  // New runbook modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newIncidentType, setNewIncidentType] = useState("");
  const [newServiceId, setNewServiceId] = useState("");
  const [newBody, setNewBody] = useState(
    "### Overview\nDescribe the failure signature.\n\n### Diagnosis\n1. Check metrics on Grafana dashboard.\n2. Query error logs: `SELECT * FROM logs WHERE level = 'ERROR'`\n\n### Mitigation Steps\n- [ ] Step 1: Scale up pod replicas.\n- [ ] Step 2: Flush Redis cache if stale keys detected.\n- [ ] Step 3: Run database vacuum if connection pool exhausted."
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchData();
  }, [selectedService]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [rList, sList] = await Promise.all([
        api.listRunbooks(selectedService === "ALL" ? undefined : selectedService),
        api.listServices(),
      ]);
      setRunbooks(rList);
      setServices(sList);
      if (rList.length > 0 && !selectedRunbook) {
        setSelectedRunbook(rList[0]);
      } else if (rList.length > 0 && selectedRunbook) {
        const found = rList.find((r) => r.id === selectedRunbook.id);
        setSelectedRunbook(found || rList[0]);
      }
    } catch (e) {
      console.error("Failed to load runbooks", e);
    } finally {
      setLoading(false);
    }
  };

  const filteredRunbooks = runbooks.filter((rb) => {
    const matchesSearch =
      rb.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rb.incident_type.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (rb.service_name && rb.service_name.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesSearch;
  });

  const handleCreateRunbook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      setSaving(true);
      const created = await api.createRunbook({
        title: newTitle,
        incident_type: newIncidentType || "General Outage",
        service_id: newServiceId ? newServiceId : undefined,
        body: newBody,
      });
      toast.success(`Created runbook: ${created.title}`, "Runbook Created");
      setShowCreateModal(false);
      setNewTitle("");
      setNewIncidentType("");
      setNewServiceId("");
      await fetchData();
      setSelectedRunbook(created);
    } catch (err: any) {
      toast.error(err.message || "Failed to create runbook", "Error");
    } finally {
      setSaving(false);
    }
  };

  const copyToClipboard = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedStep(idx);
    setTimeout(() => setCopiedStep(null), 2000);
  };

  return (
    <AppShell
      title="SRE Runbooks & Playbooks"
      subtitle="Standardized Operational Procedures"
      onIncidentCreated={fetchData}
    >
      <div className="space-y-6">
        {/* Top Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-200">
          <div className="flex items-center gap-3">
            <p className="text-xs text-slate-500 font-mono">
              Total Runbooks: <strong className="text-slate-900">{runbooks.length}</strong>
            </p>
          </div>

          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 transition-colors shadow-2xs self-start sm:self-auto"
          >
            <Plus className="h-4 w-4" />
            New SRE Runbook
          </button>
        </div>

        {/* 2-Column Split Workspace */}
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Left Column: Runbook Selector & Search */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs space-y-3">
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                type="text"
                placeholder="Search runbooks..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-1.5 text-xs text-slate-900 placeholder-slate-400 focus:border-blue-600 focus:outline-none"
              />
            </div>

            <select
              value={selectedService}
              onChange={(e) => setSelectedService(e.target.value)}
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-700 focus:border-blue-600 focus:outline-none"
            >
              <option value="ALL">All Services ({services.length})</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>

            <div className="divide-y divide-slate-100 max-h-[600px] overflow-y-auto pt-2">
              {filteredRunbooks.length === 0 ? (
                <p className="p-4 text-center text-xs text-slate-400 font-mono">No runbooks match search.</p>
              ) : (
                filteredRunbooks.map((rb) => {
                  const isSelected = selectedRunbook?.id === rb.id;
                  return (
                    <button
                      key={rb.id}
                      onClick={() => setSelectedRunbook(rb)}
                      className={`w-full text-left p-3 rounded-lg transition-colors flex items-start justify-between gap-2 ${
                        isSelected
                          ? "bg-blue-50/80 border-l-3 border-blue-600 pl-2.5"
                          : "hover:bg-slate-50"
                      }`}
                    >
                      <div>
                        <h4 className={`text-xs font-bold ${isSelected ? "text-blue-900" : "text-slate-800"}`}>
                          {rb.title}
                        </h4>
                        <div className="flex items-center gap-1.5 mt-1 text-[10px] font-mono text-slate-500">
                          <span className="rounded bg-slate-100 px-1 py-0.2">{rb.incident_type}</span>
                          {rb.service_name && (
                            <span className="text-blue-600">{rb.service_name}</span>
                          )}
                        </div>
                      </div>
                      <ChevronRight className={`h-4 w-4 shrink-0 mt-1 ${isSelected ? "text-blue-600" : "text-slate-300"}`} />
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* Right Column: Runbook Viewer & Interactive Steps */}
          <div className="lg:col-span-2 rounded-xl border border-slate-200 bg-white p-6 shadow-xs">
            {selectedRunbook ? (
              <div className="space-y-4">
                <div className="flex items-start justify-between border-b border-slate-100 pb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="rounded bg-blue-50 text-blue-700 px-2 py-0.5 text-xs font-mono font-semibold border border-blue-200">
                        {selectedRunbook.incident_type}
                      </span>
                      {selectedRunbook.service_name && (
                        <span className="rounded bg-slate-100 text-slate-700 px-2 py-0.5 text-xs font-mono border border-slate-200">
                          {selectedRunbook.service_name}
                        </span>
                      )}
                    </div>
                    <h2 className="text-xl font-bold text-slate-900">{selectedRunbook.title}</h2>
                    <p className="text-[11px] font-mono text-slate-400 mt-1">
                      Updated {new Date(selectedRunbook.updated_at).toLocaleDateString()}
                    </p>
                  </div>

                  <button
                    onClick={() => copyToClipboard(selectedRunbook.body, 999)}
                    className="flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 shadow-2xs"
                  >
                    {copiedStep === 999 ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-green-600" />
                        <span className="text-green-700 font-semibold">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5 text-slate-500" />
                        <span>Copy Markdown</span>
                      </>
                    )}
                  </button>
                </div>

                {/* Body viewer */}
                <div className="prose max-w-none text-xs leading-relaxed text-slate-700">
                  <pre className="p-4 rounded-xl border border-slate-200 bg-slate-50 font-mono text-xs text-slate-800 whitespace-pre-wrap">
                    {selectedRunbook.body}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <BookOpen className="h-10 w-10 text-slate-300 mb-2" />
                <p className="text-xs text-slate-500">Select a runbook from the left panel to inspect playbook procedures.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Runbook Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
          <div className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-modal">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
              <h3 className="text-base font-bold text-slate-900">Author SRE Runbook</h3>
              <button onClick={() => setShowCreateModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreateRunbook} className="space-y-4 text-xs">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Runbook Title *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Postgres Connection Pool Exhaustion Mitigation"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  className="form-input"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Incident Type *</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Database, Latency, OOM"
                    value={newIncidentType}
                    onChange={(e) => setNewIncidentType(e.target.value)}
                    className="form-input"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Target Service</label>
                  <select
                    value={newServiceId}
                    onChange={(e) => setNewServiceId(e.target.value)}
                    className="form-input cursor-pointer"
                  >
                    <option value="">Global / Unassigned</option>
                    {services.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Procedure Steps (Markdown)</label>
                <textarea
                  rows={8}
                  required
                  value={newBody}
                  onChange={(e) => setNewBody(e.target.value)}
                  className="form-input font-mono text-xs resize-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Publish Runbook"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
}
