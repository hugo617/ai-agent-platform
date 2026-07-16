import * as React from "react";
import {
  Area,
  AreaChart as RAreaChart,
  Bar,
  BarChart as RBarChart,
  Cell,
  Pie,
  PieChart as RPieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { useTheme } from "@/components/theme/theme-provider";
import { cn } from "@/lib/utils";

/**
 * recharts wrappers tuned to the platform design tokens.
 *
 * Three chart families: ``AreaChartMini`` (trend), ``BarChartMini`` (comparison,
 * horizontal option), ``DonutChartMini`` (share-of-whole). All pull colors from
 * the ``--chart-1..5`` CSS variables defined in index.css (light + dark sets),
 * so a theme flip re-paints them.
 *
 * recharts caveats handled here:
 *  - **Token reactivity (risk #7)**: recharts reads CSS vars at mount and does
 *    not re-render when they change. We read ``resolvedTheme`` from ThemeProvider
 *    and (a) recompute the palette array on change and (b) set it as a ``key``
 *    on the chart so React remounts it. The palette is computed each render via
 *    ``getComputedStyle``, which picks up the new token values after the
 *    ``.dark`` class flips.
 *  - **ResponsiveContainer parent height**: the consumer must give the wrapper
 *    a height (e.g. ``h-64``); ResponsiveContainer fills it.
 *  - Axis/grid styling uses ``var(--border)`` / ``var(--muted-foreground)`` for
 *    consistent contrast in both themes.
 */

/** Read the active chart palette (5 hues) from CSS vars, current-mode aware. */
function useChartColors(): string[] {
  const { resolvedTheme } = useTheme();
  // recompute whenever the theme flips so colors track the new token set. The
  // palette is read from the DOM (getComputedStyle), which reflects the new
  // .dark class after the effect runs.
  const [colors, setColors] = React.useState<string[]>(() => readPalette());
  React.useEffect(() => {
    setColors(readPalette());
  }, [resolvedTheme]);
  return colors;
}

function readPalette(): string[] {
  if (typeof window === "undefined") return [];
  const cs = getComputedStyle(document.documentElement);
  return [1, 2, 3, 4, 5].map(
    (i) => `hsl(${cs.getPropertyValue(`--chart-${i}`).trim()})`,
  );
}

/** Shared axis + grid props so all charts share tick styling. */
const axisProps = {
  tick: { fontSize: 12 },
  // Reuse muted token for axis text/borders — no hardcoded grey.
  stroke: "hsl(var(--muted-foreground))",
};

interface AreaDatum {
  label: string;
  value: number;
}

/**
 * Trend area chart. Single series, filled gradient under the line.
 * ``data`` is ``[{ label, value }, …]``; labels are usually dates/days.
 */
export function AreaChartMini({
  data,
  height = 256,
  className,
}: {
  data: AreaDatum[];
  height?: number;
  className?: string;
}) {
  const colors = useChartColors();
  const { resolvedTheme } = useTheme();
  const line = colors[0] ?? "hsl(var(--primary))";
  const grid = "hsl(var(--border))";

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RAreaChart
          // key forces remount on theme flip so the gradient re-paints.
          key={resolvedTheme}
          data={data}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={line} stopOpacity={0.35} />
              <stop offset="95%" stopColor={line} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
          <XAxis dataKey="label" {...axisProps} tickLine={false} />
          <YAxis {...axisProps} tickLine={false} width={32} />
          <Tooltip
            contentStyle={tooltipStyle()}
            cursor={{ stroke: line, strokeOpacity: 0.3 }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke={line}
            strokeWidth={2}
            fill="url(#areaFill)"
          />
        </RAreaChart>
      </ResponsiveContainer>
    </div>
  );
}

interface BarDatum {
  label: string;
  value: number;
}

/**
 * Comparison bar chart. Supports ``horizontal`` (value on X) for ranked lists
 * like a "top 10 stores" breakdown. Multi-series is out of scope here — keep it
 * one value column.
 */
export function BarChartMini({
  data,
  height = 256,
  horizontal = false,
  className,
}: {
  data: BarDatum[];
  height?: number;
  horizontal?: boolean;
  className?: string;
}) {
  const colors = useChartColors();
  const { resolvedTheme } = useTheme();
  const bar = colors[0] ?? "hsl(var(--primary))";
  const grid = "hsl(var(--border))";

  return (
    <div className={cn("w-full", className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <RBarChart
          key={resolvedTheme}
          data={data}
          layout={horizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={grid}
            horizontal={!horizontal}
            vertical={horizontal}
          />
          {horizontal ? (
            <>
              <XAxis type="number" {...axisProps} tickLine={false} />
              <YAxis
                type="category"
                dataKey="label"
                {...axisProps}
                tickLine={false}
                width={90}
              />
            </>
          ) : (
            <>
              <XAxis dataKey="label" {...axisProps} tickLine={false} />
              <YAxis {...axisProps} tickLine={false} width={32} />
            </>
          )}
          <Tooltip
            contentStyle={tooltipStyle()}
            cursor={{ fill: bar, fillOpacity: 0.08 }}
          />
          <Bar dataKey="value" fill={bar} radius={[4, 4, 0, 0]} />
        </RBarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface DonutSlice {
  label: string;
  value: number;
}

/**
 * Donut/share-of-whole chart. Each slice gets the next palette hue; the legend
 * is rendered below as label + value rows (recharts' default legend is hard to
 * theme consistently). Pass ``centerLabel`` for a centered total (e.g. "1,234").
 */
export function DonutChartMini({
  data,
  height = 256,
  centerLabel,
  className,
}: {
  data: DonutSlice[];
  height?: number;
  centerLabel?: string;
  className?: string;
}) {
  const colors = useChartColors();
  const { resolvedTheme } = useTheme();

  return (
    <div className={cn("flex w-full flex-col items-center gap-4", className)}>
      <div className="relative w-full" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <RPieChart key={resolvedTheme}>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius="60%"
              outerRadius="90%"
              paddingAngle={2}
              stroke="none"
            >
              {data.map((_, i) => (
                <Cell key={i} fill={colors[i % colors.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={tooltipStyle()} />
          </RPieChart>
        </ResponsiveContainer>
        {centerLabel && (
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold">{centerLabel}</span>
          </div>
        )}
      </div>
      {/* Legend */}
      <div className="grid w-full grid-cols-2 gap-x-4 gap-y-1.5">
        {data.map((slice, i) => (
          <div key={slice.label} className="flex items-center gap-2 text-sm">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ background: colors[i % colors.length] }}
            />
            <span className="truncate text-muted-foreground">{slice.label}</span>
            <span className="ml-auto font-medium">{slice.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Shared tooltip card style — themed via tokens so it reads in dark mode. */
function tooltipStyle(): React.CSSProperties {
  return {
    backgroundColor: "hsl(var(--popover))",
    border: "1px solid hsl(var(--border))",
    borderRadius: "0.5rem",
    color: "hsl(var(--popover-foreground))",
    fontSize: "0.75rem",
  };
}
