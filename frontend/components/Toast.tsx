"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from "lucide-react";

export type ToastType = "success" | "error" | "warning" | "info";

export interface ToastMessage {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastContextType {
  toast: {
    success: (message: string, title?: string) => void;
    error: (message: string, title?: string) => void;
    warning: (message: string, title?: string) => void;
    info: (message: string, title?: string) => void;
  };
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback(
    (type: ToastType, message: string, title?: string, duration = 4000) => {
      const id = Math.random().toString(36).substring(2, 9);
      const newToast: ToastMessage = { id, type, title, message, duration };

      setToasts((prev) => [...prev, newToast]);

      if (duration > 0) {
        setTimeout(() => {
          removeToast(id);
        }, duration);
      }
    },
    [removeToast]
  );

  const toast = {
    success: (message: string, title?: string) => addToast("success", message, title),
    error: (message: string, title?: string) => addToast("error", message, title),
    warning: (message: string, title?: string) => addToast("warning", message, title),
    info: (message: string, title?: string) => addToast("info", message, title),
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      {/* Toast viewport */}
      <div className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
        {toasts.map((t) => {
          const config = {
            success: {
              icon: CheckCircle2,
              border: "border-green-200",
              badge: "bg-green-50 text-green-700",
              titleColor: "text-green-900",
            },
            error: {
              icon: AlertCircle,
              border: "border-red-200",
              badge: "bg-red-50 text-red-700",
              titleColor: "text-red-900",
            },
            warning: {
              icon: AlertTriangle,
              border: "border-amber-200",
              badge: "bg-amber-50 text-amber-800",
              titleColor: "text-amber-900",
            },
            info: {
              icon: Info,
              border: "border-blue-200",
              badge: "bg-blue-50 text-blue-700",
              titleColor: "text-blue-900",
            },
          }[t.type];

          const Icon = config.icon;

          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 rounded-lg border ${config.border} bg-white p-3.5 shadow-elevated transition-all duration-200 animate-in slide-in-from-bottom-2`}
            >
              <div className={`rounded-md p-1.5 shrink-0 ${config.badge}`}>
                <Icon className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0 text-left">
                {t.title && <h5 className={`text-xs font-semibold ${config.titleColor}`}>{t.title}</h5>}
                <p className="text-xs text-slate-700 leading-relaxed break-words">{t.message}</p>
              </div>
              <button
                onClick={() => removeToast(t.id)}
                className="text-slate-400 hover:text-slate-700 p-0.5 rounded shrink-0 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    // Fallback safe dummy if used outside provider
    return {
      toast: {
        success: (m: string) => console.log("[Success]", m),
        error: (m: string) => console.error("[Error]", m),
        warning: (m: string) => console.warn("[Warning]", m),
        info: (m: string) => console.info("[Info]", m),
      },
    };
  }
  return context;
}
