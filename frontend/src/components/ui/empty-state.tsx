import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Whole-screen / whole-card empty state — first run, no data ever.
 *
 * Distinct from ``ListState``: ``ListState`` wraps the *table region* of a page
 * (loading skeleton / empty row / error retry); ``EmptyState`` is for the
 * *screen* — the big "you have no agents yet, create one" moment. It pairs a
 * large muted icon with a title, description, and a single primary CTA.
 *
 * Reference: Linear / Vercel empty states (restrained — a quiet icon, not a
 * heavy Aceternity-style illustration). The icon is expected to be a lucide
 * component passed via the ``icon`` prop.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  /** Primary CTA — usually a "create" button. */
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center px-6 py-16 text-center",
        className,
      )}
    >
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted">
        <Icon className="h-7 w-7 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      {description && (
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
