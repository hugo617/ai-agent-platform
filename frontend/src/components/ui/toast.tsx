import * as React from "react";
import { cn } from "@/lib/utils";

/** Lightweight toast — no external dependency. Usage: const t = useToast(); t.success("saved") */

type ToastVariant = "default" | "success" | "destructive";

interface ToastItem {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  push: (t: Omit<ToastItem, "id">) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);
  const idRef = React.useRef(0);

  const remove = React.useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = React.useCallback(
    (t: Omit<ToastItem, "id">) => {
      const id = ++idRef.current;
      setItems((prev) => [...prev, { ...t, id }]);
      setTimeout(() => remove(id), 4000);
    },
    [remove]
  );

  const value = React.useMemo<ToastContextValue>(
    () => ({
      push,
      success: (title, description) =>
        push({ title, description, variant: "success" }),
      error: (title, description) =>
        push({ title, description, variant: "destructive" }),
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto rounded-md border p-4 shadow-lg",
              t.variant === "success" &&
                "border-emerald-200 bg-emerald-50 text-emerald-900",
              t.variant === "destructive" &&
                "border-red-200 bg-red-50 text-red-900",
              t.variant === "default" && "border-border bg-background"
            )}
          >
            <div className="text-sm font-semibold">{t.title}</div>
            {t.description && (
              <div className="mt-1 text-xs opacity-80">{t.description}</div>
            )}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
