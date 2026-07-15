import * as React from "react";
import { useId } from "react";
import { Label } from "@/components/ui/label";

/**
 * Shared labelled form field wrapper.
 *
 * Replaces the per-page ``Field`` component copy-pasted across 7 page files
 * (customers/users/roles/groups/members/profile/billing-admin), which drifted
 * into three near-duplicate shapes (``space-y-1.5`` vs ``space-y-2``, with vs
 * without ``hint``). This single component covers all of them and additionally
 * associates the ``<Label>`` with its input via a generated id (the local
 * copies never wired ``htmlFor``, so screen readers couldn't link them).
 *
 * Pass ``htmlFor`` to bind the label to a specific input id (needed for
 * react-hook-form ``register``-style inputs that own their id); otherwise the
 * component generates one and exposes it via the render-prop form
 * ``children(id)``. Most call sites don't need the id and just pass JSX.
 */
export function FormField({
  label,
  error,
  hint,
  htmlFor,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  /** Bind the label to a specific input id. Optional — auto-generated if absent. */
  htmlFor?: string;
  /** Either a ReactNode, or a function that receives the generated id. */
  children: React.ReactNode | ((id: string) => React.ReactNode);
}) {
  const autoId = useId();
  const id = htmlFor ?? autoId;
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-sm font-medium">
        {label}
      </Label>
      {typeof children === "function" ? children(id) : children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
