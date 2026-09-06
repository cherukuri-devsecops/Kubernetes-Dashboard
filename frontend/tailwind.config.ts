import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#090d14",
          900: "#101722",
          850: "#17202d",
          800: "#1f2937",
        },
        signal: {
          green: "#31d0aa",
          amber: "#f5c66a",
          red: "#ff6b6b",
          blue: "#6ea8fe",
        },
        brand: {
          DEFAULT: "#8b5cf6",
          400: "#a78bfa",
          500: "#8b5cf6",
          600: "#7c3aed",
        },
        app: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-hover": "var(--color-surface-hover)",
        line: "var(--color-border)",
        "line-strong": "var(--color-border-strong)",
        content: {
          primary: "var(--color-text-primary)",
          secondary: "var(--color-text-secondary)",
          muted: "var(--color-text-muted)",
        },
      },
      boxShadow: {
        panel: "0 20px 50px rgba(0, 0, 0, 0.28)",
      },
    },
  },
  plugins: [],
} satisfies Config;
