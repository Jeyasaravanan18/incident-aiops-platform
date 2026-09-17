"use client";

import React, { useState, useEffect } from "react";
import { AlertCircle, AlertTriangle, Flame, ShieldAlert, X } from "lucide-react";
import { api, Service } from "../lib/api";
import { useToast } from "./Toast";

interface DeclareIncidentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIncidentCreated?: () => void;
}

export default function DeclareIncidentModal({
  isOpen,
  onClose,
  onIncidentCreated,
}: DeclareIncidentModalProps) {
  const { toast } = useToast();
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    title: "",
    service_id: "",
    severity: "SEV2",
    description: "",
  });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      api.listServices().then(setServices).catch(() => {});
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim() || !formData.service_id) {
      setError("Incident Title and Service are required.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const created = await api.createIncident(formData);
      toast.success(`Incident declared: ${created.title}`, "Incident Declared");
      onClose();
      setFormData({ title: "", service_id: "", severity: "SEV2", description: "" });
      if (onIncidentCreated) onIncidentCreated();
    } catch (err: any) {
      setError(err.message || "Failed to declare incident");
      toast.error(err.message || "Failed to declare incident", "Error");
    } finally {
      setLoading(false);
    }
  };

  const severityGuide: Record<string, { label: string; desc: string; color: string; badge: string }> = {
    SEV1: {
      label: "SEV1 - Critical Outage",
      desc: "Complete service outage or severe revenue/customer impact. 15-min MTTA SLA.",
      color: "border-red-500 bg-red-50 text-red-700",
      badge: "bg-red-600 text-white",
    },
    SEV2: {
      label: "SEV2 - Severe Degradation",
      desc: "Critical system component degraded, high error rates, no direct workaround.",
      color: "border-orange-500 bg-orange-50 text-orange-800",
      badge: "bg-orange-500 text-white",
    },
    SEV3: {
      label: "SEV3 - Moderate Impact",
      desc: "Minor customer impact or impaired redundancy. Core workflow remains functional.",
      color: "border-amber-500 bg-amber-50 text-amber-800",
      badge: "bg-amber-500 text-white",
    },
    SEV4: {
      label: "SEV4 - Low / Minor",
      desc: "Non-critical glitch, cosmetic bug, or internal tooling impairment.",
      color: "border-blue-500 bg-blue-50 text-blue-800",
      badge: "bg-blue-600 text-white",
    },
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4 backdrop-blur-xs">
      <div className="w-full max-w-lg rounded-xl border border-slate-200 bg-white p-6 shadow-modal animate-in fade-in-0 zoom-in-95">
        <div className="flex items-center justify-between border-b border-slate-100 pb-4 mb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-50 text-red-600 border border-red-100">
              <Flame className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-slate-900">Declare Production Incident</h3>
              <p className="text-xs text-slate-500">Triggers pager escalation & SRE war room mobilization</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Incident Title <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              placeholder="e.g. Payment Gateway elevated 5xx rate across US-East"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              className="form-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Affected Service <span className="text-red-500">*</span>
              </label>
              <select
                required
                value={formData.service_id}
                onChange={(e) => setFormData({ ...formData, service_id: e.target.value })}
                className="form-input cursor-pointer"
              >
                <option value="">Select Service...</option>
                {services.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.criticality})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Severity Level <span className="text-red-500">*</span>
              </label>
              <select
                value={formData.severity}
                onChange={(e) => setFormData({ ...formData, severity: e.target.value })}
                className="form-input cursor-pointer font-medium"
              >
                <option value="SEV1">SEV1 - Critical Outage</option>
                <option value="SEV2">SEV2 - Severe Degradation</option>
                <option value="SEV3">SEV3 - Moderate Impact</option>
                <option value="SEV4">SEV4 - Low / Minor</option>
              </select>
            </div>
          </div>

          {/* Severity guidance preview */}
          <div className={`rounded-lg border p-2.5 text-[11px] ${severityGuide[formData.severity]?.color}`}>
            <p className="font-semibold">{severityGuide[formData.severity]?.label}</p>
            <p className="mt-0.5 opacity-90">{severityGuide[formData.severity]?.desc}</p>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 mb-1">
              Description & Initial Symptoms
            </label>
            <textarea
              rows={3}
              placeholder="What telemetry alerted? Error symptoms? Impacted customers?"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="form-input resize-none"
            />
          </div>

          <div className="flex items-center justify-end gap-2.5 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-200 px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-xs font-semibold text-white shadow-xs hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              <Flame className="h-3.5 w-3.5" />
              {loading ? "Declaring..." : "Declare Incident"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
