import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#ffffff",
        card: "#ffffff",
        panel: "#f8fafc",
        panelHover: "#f1f5f9",
        hover: "#f1f5f9",
        line: "#e2e8f0",
        border: "#e2e8f0",
        borderDark: "#cbd5e1",
        accent: "#2563eb",
        accentDark: "#1d4ed8",
        accentLight: "#eff6ff",
        accentText: "#1d4ed8",
        success: "#16a34a",
        successLight: "#f0fdf4",
        successDark: "#15803d",
        warning: "#d97706",
        danger: "#dc2626",
        textPrimary: "#09090b",
        textSecondary: "#475569",
        textMuted: "#64748b",
        sev1: "#dc2626",
        sev2: "#ea580c",
        sev3: "#d97706",
        sev4: "#2563eb",
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Inter", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        subtle: "0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05)",
        card: "0 1px 3px 0 rgba(15, 23, 42, 0.06), 0 1px 2px -1px rgba(15, 23, 42, 0.04)",
        elevated: "0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.05)",
        modal: "0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.1)",
      },
    },
  },
  plugins: [],
};

export default config;
