"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BookOpen,
  FileText,
  Layers,
  Plus,
  ScrollText,
  Search,
  Settings,
  ShieldAlert,
  X,
} from "lucide-react";

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenDeclare: () => void;
}

export default function CommandPalette({ isOpen, onClose, onOpenDeclare }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const commands = [
    {
      id: "declare",
      label: "Declare Production Incident",
      category: "Quick Actions",
      icon: Plus,
      color: "text-red-600 bg-red-50",
      action: () => {
        onClose();
        onOpenDeclare();
      },
    },
    {
      id: "dashboard",
      label: "Operations Command Dashboard",
      category: "Navigation",
      icon: Activity,
      color: "text-blue-600 bg-blue-50",
      action: () => {
        router.push("/");
        onClose();
      },
    },
    {
      id: "incidents",
      label: "Incident Triage Queue",
      category: "Navigation",
      icon: AlertTriangle,
      color: "text-amber-600 bg-amber-50",
      action: () => {
        router.push("/incidents");
        onClose();
      },
    },
    {
      id: "alerts",
      label: "Correlated Alerts & Deduplication",
      category: "Navigation",
      icon: ShieldAlert,
      color: "text-purple-600 bg-purple-50",
      action: () => {
        router.push("/alerts");
        onClose();
      },
    },
    {
      id: "services",
      label: "Service Catalog & Topology",
      category: "Navigation",
      icon: Layers,
      color: "text-emerald-600 bg-emerald-50",
      action: () => {
        router.push("/services");
        onClose();
      },
    },
    {
      id: "logs",
      label: "Structured Log Explorer",
      category: "Navigation",
      icon: ScrollText,
      color: "text-slate-700 bg-slate-100",
      action: () => {
        router.push("/logs");
        onClose();
      },
    },
    {
      id: "runbooks",
      label: "SRE Runbooks & Playbooks",
      category: "Navigation",
      icon: BookOpen,
      color: "text-blue-600 bg-blue-50",
      action: () => {
        router.push("/runbooks");
        onClose();
      },
    },
    {
      id: "postmortems",
      label: "Blameless Postmortems",
      category: "Navigation",
      icon: FileText,
      color: "text-green-600 bg-green-50",
      action: () => {
        router.push("/postmortems");
        onClose();
      },
    },
    {
      id: "analytics",
      label: "Reliability & SLO Analytics",
      category: "Navigation",
      icon: BarChart3,
      color: "text-indigo-600 bg-indigo-50",
      action: () => {
        router.push("/analytics");
        onClose();
      },
    },
    {
      id: "settings",
      label: "Platform Settings & RBAC Switcher",
      category: "Navigation",
      icon: Settings,
      color: "text-slate-700 bg-slate-100",
      action: () => {
        router.push("/settings");
        onClose();
      },
    },
  ];

  const filtered = commands.filter((c) =>
    c.label.toLowerCase().includes(query.toLowerCase()) ||
    c.category.toLowerCase().includes(query.toLowerCase())
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (isOpen) onClose();
        else onClose(); // parent handles toggle
      }
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-900/30 p-4 pt-20 backdrop-blur-xs">
      <div className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-2 shadow-modal animate-in fade-in-0 zoom-in-95">
        <div className="relative flex items-center border-b border-slate-100 px-3 pb-2.5 pt-1">
          <Search className="h-4 w-4 text-slate-400 mr-2.5" />
          <input
            type="text"
            placeholder="Type a command or jump to page... (e.g. Incidents, Declare, Logs)"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
            className="w-full bg-transparent text-sm text-slate-900 placeholder-slate-400 focus:outline-none"
          />
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <p className="p-4 text-center text-xs text-slate-400">No commands found matching "{query}"</p>
          ) : (
            <div className="space-y-1">
              {filtered.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={item.action}
                    className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs text-slate-700 hover:bg-blue-50/70 hover:text-blue-900 transition-colors group"
                  >
                    <div className="flex items-center gap-2.5">
                      <div className={`flex h-7 w-7 items-center justify-center rounded-md ${item.color}`}>
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                      <span className="font-medium">{item.label}</span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono group-hover:text-blue-600">
                      {item.category}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-100 px-3 pt-2 text-[11px] text-slate-400">
          <span>Tip: Press <kbd className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[10px] text-slate-600 border border-slate-200">ESC</kbd> to close</span>
          <span>IncidentOps Command</span>
        </div>
      </div>
    </div>
  );
}
