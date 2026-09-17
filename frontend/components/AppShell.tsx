"use client";

import React, { useState } from "react";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { ToastProvider } from "./Toast";

interface AppShellProps {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  breadcrumbs?: { label: string; href?: string }[];
  activeIncidentsCount?: number;
  openAlertsCount?: number;
  onIncidentCreated?: () => void;
}

export default function AppShell({
  children,
  title,
  subtitle,
  breadcrumbs,
  activeIncidentsCount,
  openAlertsCount,
  onIncidentCreated,
}: AppShellProps) {
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  return (
    <ToastProvider>
      <div className="flex min-h-screen bg-white text-slate-900 selection:bg-blue-100 selection:text-blue-900">
        {/* Navigation Sidebar */}
        <Sidebar
          isMobileOpen={isMobileNavOpen}
          onCloseMobile={() => setIsMobileNavOpen(false)}
          activeIncidentsCount={activeIncidentsCount}
          openAlertsCount={openAlertsCount}
        />

        {/* Main Content Area */}
        <div className="flex min-h-screen flex-1 flex-col lg:pl-64 bg-white">
          <Header
            title={title}
            subtitle={subtitle}
            breadcrumbs={breadcrumbs}
            onIncidentCreated={onIncidentCreated}
            onOpenMobileMenu={() => setIsMobileNavOpen(true)}
          />

          <main className="flex-1 bg-white p-4 sm:p-6 lg:p-8">
            {children}
          </main>
        </div>
      </div>
    </ToastProvider>
  );
}
