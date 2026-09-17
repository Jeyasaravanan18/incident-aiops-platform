"use client";

import React, { useEffect, useState } from "react";
import {
  Bell,
  BellOff,
  Flame,
  Menu,
  Radio,
  Search,
} from "lucide-react";
import { wsClient } from "../lib/websocket";
import DeclareIncidentModal from "./DeclareIncidentModal";
import CommandPalette from "./CommandPalette";

interface HeaderProps {
  title?: string;
  subtitle?: string;
  breadcrumbs?: { label: string; href?: string }[];
  onIncidentCreated?: () => void;
  onOpenMobileMenu?: () => void;
}

export default function Header({
  title = "Operations Command",
  subtitle,
  breadcrumbs,
  onIncidentCreated,
  onOpenMobileMenu,
}: HeaderProps) {
  const [wsConnected, setWsConnected] = useState(false);
  const [isDeclareOpen, setIsDeclareOpen] = useState(false);
  const [isCommandOpen, setIsCommandOpen] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(false);

  useEffect(() => {
    const disconnect = wsClient.connect("dashboard", () => {
      setWsConnected(true);
    });
    setWsConnected(true);

    // Keyboard shortcut for Cmd+K
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsCommandOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      disconnect();
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  return (
    <>
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 bg-white/95 px-4 sm:px-6 backdrop-blur-md">
        <div className="flex items-center gap-3">
          {/* Mobile hamburger */}
          <button
            onClick={onOpenMobileMenu}
            className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>

          <div>
            {breadcrumbs && breadcrumbs.length > 0 ? (
              <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
                {breadcrumbs.map((b, idx) => (
                  <React.Fragment key={idx}>
                    {idx > 0 && <span className="text-slate-300">/</span>}
                    {b.href ? (
                      <a href={b.href} className="hover:text-blue-600 transition-colors">
                        {b.label}
                      </a>
                    ) : (
                      <span className="text-slate-900 font-semibold">{b.label}</span>
                    )}
                  </React.Fragment>
                ))}
              </div>
            ) : (
              <div>
                {subtitle && (
                  <p className="text-[10px] font-mono uppercase tracking-wider text-blue-600 font-semibold leading-none mb-0.5">
                    {subtitle}
                  </p>
                )}
                <h1 className="text-base font-bold tracking-tight text-slate-900 leading-tight">
                  {title}
                </h1>
              </div>
            )}
          </div>
        </div>

        {/* Right Action Cluster */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Command Palette Trigger */}
          <button
            onClick={() => setIsCommandOpen(true)}
            className="hidden sm:flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50/80 px-2.5 py-1.5 text-xs text-slate-500 hover:border-slate-300 hover:bg-slate-100/80 transition-colors"
          >
            <Search className="h-3.5 w-3.5 text-slate-400" />
            <span>Search or command...</span>
            <kbd className="rounded border border-slate-200 bg-white px-1.5 py-0.2 text-[10px] font-mono text-slate-500 shadow-2xs">
              ⌘K
            </kbd>
          </button>

          {/* WebSocket Status */}
          <div className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-mono text-slate-700">
            <Radio className={`h-3 w-3 ${wsConnected ? "text-green-600 animate-pulse" : "text-amber-500"}`} />
            <span className={wsConnected ? "text-green-700 font-semibold" : "text-amber-600"}>
              {wsConnected ? "LIVE" : "SYNCING"}
            </span>
          </div>

          {/* Sound Notification Toggle */}
          <button
            onClick={() => setSoundEnabled(!soundEnabled)}
            title={soundEnabled ? "Mute audio alerts" : "Enable audio alerts"}
            className={`rounded-lg p-1.5 border transition-colors ${
              soundEnabled
                ? "border-blue-200 bg-blue-50 text-blue-700"
                : "border-slate-200 bg-white text-slate-400 hover:bg-slate-50 hover:text-slate-600"
            }`}
          >
            {soundEnabled ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
          </button>

          {/* Declare Incident Button */}
          <button
            onClick={() => setIsDeclareOpen(true)}
            className="flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-red-700 transition-colors shrink-0"
          >
            <Flame className="h-3.5 w-3.5" />
            <span className="hidden xs:inline">Declare Incident</span>
            <span className="xs:hidden">Declare</span>
          </button>
        </div>
      </header>

      {/* Declare Incident Modal */}
      <DeclareIncidentModal
        isOpen={isDeclareOpen}
        onClose={() => setIsDeclareOpen(false)}
        onIncidentCreated={onIncidentCreated}
      />

      {/* Command Palette Modal */}
      <CommandPalette
        isOpen={isCommandOpen}
        onClose={() => setIsCommandOpen(false)}
        onOpenDeclare={() => setIsDeclareOpen(true)}
      />
    </>
  );
}
