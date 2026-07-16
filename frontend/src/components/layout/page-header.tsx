import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Unified page header — title + subtitle + right-aligned actions.
 *
 * Replaces the copy-pasted `<h1 className="text-3xl font-bold tracking-tight">`
 * + muted subtitle + `ml-auto` action button pattern found across 16 page
 * heads. Every page used to hand-roll the same flex row; this component is the
 * single source so the spacing, type scale, and responsive wrap stay consistent.
 *
 * Usage: `<PageHeader title="智能体" subtitle="…" actions={<Button/>} />`.
 * The actions slot collapses below the title on small screens (flex-wrap).
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  className,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  /** Right-aligned action(s) — usually a primary button or a refresh control. */
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between",
        className,
      )}
    >
      <div className="min-w-0 space-y-1">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
          {title}
        </h1>
        {subtitle && (
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}
