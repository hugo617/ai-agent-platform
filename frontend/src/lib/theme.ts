/**
 * Theme-color application for tenant white-label branding (priority 52).
 *
 * The shadcn design tokens are CSS variables in *space-separated HSL* format
 * (e.g. ``--primary: 222.2 47.4% 11.2%``), consumed by Tailwind via
 * ``hsl(var(--primary))``. The tenant's ``theme_color`` is stored as
 * ``#RRGGBB``, so this module converts it to that HSL string and writes it onto
 * ``:root`` (replacing ``--primary``), picking a readable
 * ``--primary-foreground`` (black/white by luminance contrast) at the same time.
 *
 * Only ``--primary`` is overridden — the rest of the palette stays at the
 * platform default, so a tenant picks an accent color without reskinning every
 * surface. ``applyThemeColor(null)`` restores the defaults captured at load.
 */

// The platform-default HSL values, captured once at module load so any tenant
// override can be cleanly reverted (logout / tenant switch / theme cleared).
const DEFAULT_PRIMARY = readCssVar("--primary") ?? "222.2 47.4% 11.2%";
const DEFAULT_PRIMARY_FOREGROUND =
  readCssVar("--primary-foreground") ?? "210 40% 98%";

function readCssVar(name: string): string | undefined {
  if (typeof window === "undefined") return undefined;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name);
  return v.trim() || undefined;
}

/** Convert a ``#RRGGBB`` string to the shadcn HSL token format ``H S% L%``. */
export function hexToHsl(hex: string): string {
  const m = /^#([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) return DEFAULT_PRIMARY;
  const n = Number.parseInt(m[1], 16);
  const r = ((n >> 16) & 0xff) / 255;
  const g = ((n >> 8) & 0xff) / 255;
  const b = (n & 0xff) / 255;

  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
        break;
      case g:
        h = ((b - r) / d + 2) * 60;
        break;
      default:
        h = ((r - g) / d + 4) * 60;
        break;
    }
  }
  return `${h.toFixed(1)} ${(s * 100).toFixed(1)}% ${(l * 100).toFixed(1)}%`;
}

/** Relative luminance of a ``#RRGGBB`` color (sRGB, 0–1). */
function relativeLuminance(hex: string): number {
  const m = /^#([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) return 0;
  const n = Number.parseInt(m[1], 16);
  const chan = (shift: number) => {
    const c = ((n >> shift) & 0xff) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * chan(16) + 0.7152 * chan(8) + 0.0722 * chan(0);
}

/**
 * Apply a tenant theme color as the global ``--primary`` token.
 *
 * Writes the converted HSL onto ``:root`` and chooses a
 * ``--primary-foreground`` (near-white or near-black) by WCAG luminance
 * contrast so button text stays readable on any chosen color. Passing ``null``
 * (or an invalid value) restores the platform defaults.
 */
export function applyThemeColor(hex: string | null | undefined): void {
  if (typeof window === "undefined") return;
  const root = document.documentElement;
  if (!hex) {
    root.style.setProperty("--primary", DEFAULT_PRIMARY);
    root.style.setProperty("--primary-foreground", DEFAULT_PRIMARY_FOREGROUND);
    return;
  }
  root.style.setProperty("--primary", hexToHsl(hex));
  // Pick the foreground by luminance contrast against the theme color. The
  // near-black/near-white pair is the same family shadcn uses by default.
  root.style.setProperty(
    "--primary-foreground",
    relativeLuminance(hex) > 0.45 ? "222.2 47.4% 11.2%" : "0 0% 100%",
  );
}
