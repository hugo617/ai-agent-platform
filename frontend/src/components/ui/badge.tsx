import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
        secondary:
          "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive:
          "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
        outline: "text-foreground",
        success:
          "border-transparent bg-emerald-500 text-white hover:bg-emerald-500/80",
        /** Muted pill with a leading status dot — "运行中" / "已停用" etc. The
         *  dot is drawn via ::before so it travels with the badge and stays a
         *  fixed size. Pair with a short status word (not a long label). */
        dot: "border-transparent bg-muted text-muted-foreground [&::before]:mr-1.5 [&::before]:h-1.5 [&::before]:w-1.5 [&::before]:rounded-full [&::before]:bg-current",
        /** Dot variant tinted success (green dot). Use for "active/running". */
        "dot-success":
          "border-transparent bg-muted text-muted-foreground [&::before]:mr-1.5 [&::before]:h-1.5 [&::before]:w-1.5 [&::before]:rounded-full [&::before]:bg-emerald-500",
        /** Dot variant tinted warning (amber dot). Use for "pending/idle". */
        "dot-warning":
          "border-transparent bg-muted text-muted-foreground [&::before]:mr-1.5 [&::before]:h-1.5 [&::before]:w-1.5 [&::before]:rounded-full [&::before]:bg-amber-500",
        /** Dot variant tinted destructive (red dot). Use for "failed/stopped". */
        "dot-destructive":
          "border-transparent bg-muted text-muted-foreground [&::before]:mr-1.5 [&::before]:h-1.5 [&::before]:w-1.5 [&::before]:rounded-full [&::before]:bg-red-500",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
