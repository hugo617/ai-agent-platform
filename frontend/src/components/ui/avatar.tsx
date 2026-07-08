import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A minimal avatar — renders the user's initials in a colored circle. No image
 * hosting required; matches the existing "no external deps" aesthetic.
 */

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  src?: string | null;
  name?: string | null;
  size?: "sm" | "md" | "lg";
}

const SIZE_CLASS: Record<NonNullable<AvatarProps["size"]>, string> = {
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-12 w-12 text-base",
};

function initials(name?: string | null): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const COLOR_PALETTE = [
  "bg-blue-500", "bg-emerald-500", "bg-amber-500", "bg-rose-500",
  "bg-violet-500", "bg-cyan-500", "bg-orange-500", "bg-pink-500",
];

function colorFor(name?: string | null): string {
  if (!name) return COLOR_PALETTE[0];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return COLOR_PALETTE[Math.abs(hash) % COLOR_PALETTE.length];
}

export const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(
  ({ className, src, name, size = "md", ...props }, ref) => {
    // The backend defaults avatar to "/avatars/default.jpg" but serves no
    // static mount for that path, so treat it as "no avatar" and fall back to
    // initials. Once a real avatar upload exists this guard is a no-op.
    const effectiveSrc =
      src && src !== "/avatars/default.jpg" ? src : null;
    if (effectiveSrc) {
      return (
        <div
          ref={ref}
          className={cn(
            "relative flex shrink-0 overflow-hidden rounded-full",
            SIZE_CLASS[size],
            className
          )}
          {...props}
        >
          <img src={effectiveSrc} alt={name ?? "avatar"} className="aspect-square h-full w-full object-cover" />
        </div>
      );
    }
    return (
      <div
        ref={ref}
        className={cn(
          "flex shrink-0 items-center justify-center rounded-full font-medium text-white",
          SIZE_CLASS[size],
          colorFor(name),
          className
        )}
        {...props}
      >
        {initials(name)}
      </div>
    );
  }
);
Avatar.displayName = "Avatar";
