import * as React from "react";

/**
 * Lightweight theme provider — dark/light/system, no third-party dep.
 *
 * The platform ships its full dark palette in ``index.css`` (``.dark`` token
 * block), but nothing was wiring the ``.dark`` class onto ``<html>``. This
 * provider closes that gap: it persists the choice (``light`` / ``dark`` /
 * ``system``) in ``localStorage``, toggles the ``.dark`` class on
 * ``document.documentElement``, and follows the OS preference when set to
 * ``system``.
 *
 * Placement (per the UI revamp plan): inside ``QueryClientProvider``, outside
 * ``ToastProvider`` — a theme switch must not re-render the toast tree. It also
 * has to sit *outside* the layout that runs ``useApplyTenantTheme``, so the
 * tenant branding hook can subscribe to theme changes and re-derive its
 * foreground contrast (see ``lib/theme.ts`` — the dark branch needs to know the
 * active theme).
 *
 * Re-rendering strategy on theme change: consumers read ``theme`` /
 * ``resolvedTheme`` from context and re-render naturally. Chart components that
 * can't react to CSS-variable changes (recharts) read ``resolvedTheme`` and use
 * it as a ``key`` or effect dependency to force a re-paint.
 */

export type Theme = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "theme";

interface ThemeContextValue {
  /** The user's stored preference. */
  theme: Theme;
  /** The theme actually applied after resolving ``system``. */
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

/** The theme currently in effect, accounting for the ``system`` preference. */
function getSystemTheme(): ResolvedTheme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function resolve(theme: Theme): ResolvedTheme {
  return theme === "system" ? getSystemTheme() : theme;
}

function applyThemeClass(resolved: ResolvedTheme) {
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = React.useState<Theme>(() => {
    if (typeof window === "undefined") return "system";
    return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? "system";
  });

  const [resolvedTheme, setResolvedTheme] = React.useState<ResolvedTheme>(() =>
    resolve(theme),
  );

  // Apply the class whenever the preference or the OS scheme changes.
  React.useEffect(() => {
    const resolved = resolve(theme);
    setResolvedTheme(resolved);
    applyThemeClass(resolved);

    if (theme === "system") {
      // Follow OS changes only while in ``system`` mode.
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      const onChange = () => {
        const next = getSystemTheme();
        setResolvedTheme(next);
        applyThemeClass(next);
      };
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    }
  }, [theme]);

  const setTheme = React.useCallback((next: Theme) => {
    localStorage.setItem(STORAGE_KEY, next);
    setThemeState(next);
  }, []);

  const toggleTheme = React.useCallback(() => {
    setThemeState((prev) => {
      const current = resolve(prev);
      const next: Theme = current === "dark" ? "light" : "dark";
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  const value = React.useMemo<ThemeContextValue>(
    () => ({ theme, resolvedTheme, setTheme, toggleTheme }),
    [theme, resolvedTheme, setTheme, toggleTheme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}
