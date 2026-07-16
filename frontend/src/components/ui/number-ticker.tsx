import { useEffect } from "react";
import { animate, motion, useMotionValue, useTransform } from "motion/react";
import { cn } from "@/lib/utils";

/**
 * Number Ticker — animates a number from its previous value to the new one.
 *
 * This is one of the four motion use cases sanctioned by the revamp plan
 * (§7 P1-8): Dashboard metric cards. It counts up on mount and whenever the
 * target value changes (e.g. after a refetch).
 *
 * Implementation note: we drive a ``useMotionValue`` with the imperative
 * ``animate()`` and render the rounded value through ``useTransform`` inside a
 * ``motion.span``. This means the animation runs entirely on the motion side —
 * no React re-render per frame, so a dashboard with several tickers stays smooth.
 *
 * ``format`` defaults to ``toLocaleString()`` (thousands separators); pass a
 * custom formatter for currency / decimals.
 */
export function NumberTicker({
  value,
  duration = 0.9,
  className,
  format = (n: number) => Math.round(n).toLocaleString(),
}: {
  value: number;
  /** Animation length in seconds. */
  duration?: number;
  className?: string;
  /** Format the (rounded) number for display. */
  format?: (n: number) => string;
}) {
  const mv = useMotionValue(0);
  const text = useTransform(mv, format);

  useEffect(() => {
    const controls = animate(mv, value, {
      duration,
      ease: "easeOut",
    });
    return () => controls.stop();
  }, [mv, value, duration]);

  return (
    <motion.span className={cn("tabular-nums", className)}>{text}</motion.span>
  );
}
