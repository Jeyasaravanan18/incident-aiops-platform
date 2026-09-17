"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BookOpen,
  FileText,
  Layers,
  LogOut,
  ScrollText,
  Settings,
  ShieldAlert,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { clearTokens, User, api } from "../lib/api";

const navItems = [
  { label: "Dashboard", href: "/", icon: Activity },
  { label: "Incidents", href: "/incidents", icon: AlertTriangle, hasBadge: "incidents" },
  { label: "Alerts", href: "/alerts", icon: ShieldAlert, hasBadge: "alerts" },
  { label: "Services", href: "/services", icon: Layers },
  { label: "Log Explorer", href: "/logs", icon: ScrollText },
  { label: "Runbooks", href: "/runbooks", icon: BookOpen },
  { label: "Postmortems", href: "/postmortems", icon: FileText },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Settings", href: "/settings", icon: Settings },
];

interface SidebarProps {
  isMobileOpen?: boolean;
  onCloseMobile?: () => void;
  activeIncidentsCount?: number;
  openAlertsCount?: number;
}

export default function Sidebar({
  isMobileOpen = false,
  onCloseMobile,
  activeIncidentsCount,
  openAlertsCount,
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<User | null>(null);

  useEffect(() => {
    const raw = localStorage.getItem("incidentops_user");
    if (raw) {
      try {
        setCurrentUser(JSON.parse(raw));
      } catch (e) {
        // ignore
      }
    } else {
      api.getMe().then((u) => {
        setCurrentUser(u);
        localStorage.setItem("incidentops_user", JSON.stringify(u));
      }).catch(() => {});
    }
  }, []);

  const handleLogout = () => {
    clearTokens();
    router.push("/login");
  };

  const navContent = (
    <div className="flex h-full flex-col justify-between p-4 bg-white">
      <div>
        {/* Brand Header */}
        <div className="mb-6 flex items-center justify-between px-2 pt-1">
          <Link href="/" className="flex items-center gap-2.5 text-base font-bold tracking-tight text-slate-900">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white shadow-xs">
              <ShieldAlert className="h-4.5 w-4.5" />
            </div>
            <div className="flex items-baseline gap-1">
              <span>Incident<span className="text-blue-600">Ops</span></span>
              <span className="text-[10px] font-mono text-slate-400">SRE</span>
            </div>
          </Link>
          <div className="flex items-center gap-1.5">
            <span className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] font-mono font-medium text-blue-700">
              v1.0
            </span>
            {isMobileOpen && onCloseMobile && (
              <button
                onClick={onCloseMobile}
                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 lg:hidden"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={onCloseMobile}
                className={`flex items-center justify-between rounded-lg px-3 py-2 text-xs font-medium transition-all ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-semibold border-l-3 border-blue-600 pl-2.5"
                    : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <Icon className={`h-4 w-4 ${isActive ? "text-blue-600" : "text-slate-400"}`} />
                  <span>{item.label}</span>
                </div>

                {item.hasBadge === "incidents" && (activeIncidentsCount ?? 0) > 0 && (
                  <span className="rounded-full bg-red-100 px-1.5 py-0.5 text-[10px] font-mono font-bold text-red-700">
                    {activeIncidentsCount}
                  </span>
                )}

                {item.hasBadge === "alerts" && (openAlertsCount ?? 0) > 0 && (
                  <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-mono font-bold text-amber-800">
                    {openAlertsCount}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer System Status & User Info */}
      <div className="space-y-3 pt-3 border-t border-slate-100">
        {/* System Health Card */}
        <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-2.5 text-xs">
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-500 text-[11px] font-medium">Cluster Env</span>
            <span className="font-mono text-[11px] text-green-700 font-semibold flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse-slow"></span>
              PRODUCTION
            </span>
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
            <span>Broker: Redis PubSub</span>
            <span>Workers: 2 Online</span>
          </div>
        </div>

        {/* User Card */}
        <div className="flex items-center justify-between rounded-lg p-1.5 hover:bg-slate-50 transition-colors">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-100 text-blue-700 text-xs font-bold shrink-0">
              {(currentUser?.full_name || "A")[0]}
            </div>
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-slate-800">
                {currentUser?.full_name || "Avery Morgan"}
              </p>
              <span className="inline-block rounded bg-slate-100 px-1.5 py-0.2 text-[9px] font-mono uppercase text-slate-600 font-medium">
                {currentUser?.role || "ADMIN"}
              </span>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="rounded p-1.5 text-slate-400 hover:bg-slate-200/60 hover:text-red-600 transition-colors"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="fixed left-0 top-0 z-30 hidden h-full w-64 flex-col border-r border-slate-200 bg-white lg:flex">
        {navContent}
      </aside>

      {/* Mobile Slide-over Drawer */}
      {isMobileOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div
            className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
            onClick={onCloseMobile}
          />
          <div className="relative w-64 max-w-xs flex-1 bg-white shadow-xl z-10 animate-in slide-in-from-left duration-200">
            {navContent}
          </div>
        </div>
      )}
    </>
  );
}
