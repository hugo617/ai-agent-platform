/**
 * Theme-color application for tenant white-label branding (priority 52).
 *
 * The shadcn design tokens are CSS variables in *space-separated HSL* format
 * (e.g. ``--primary: 222.2 47.4% 11.2%``), consumed by Tailwind via
 * ``hsl(var(--primary))``. The tenant's ``theme_color`` is stored as
 * ``#RRGGBB``, so this module converts it to that HSL string and writes it onto
 * ``:root`` (replacing ``--primary``), picking a readable
 * ``--primary-foreground`` (black/white by WCAG contrast) at the same time.
 *
 * Only ``--primary`` is overridden — the rest of the palette stays at the
 * platform default, so a tenant picks an accent color without reskinning every
 * surface. ``applyThemeColor(null)`` restores the defaults.
 *
 * Dark-mode awareness (P0): the platform default ``--primary`` differs between
 * light and dark, and so does its foreground. The tenant's brand color is
 * applied identically in both modes (a red brand is red everywhere), and its
 * foreground is picked by contrast against the brand color *itself* — which is
 * mode-independent, because ``--primary`` always paints buttons/accents/links,
 * never page backgrounds. But the *revert* path must restore the mode-specific
 * platform default, and the brand must be re-applied on theme flip; see
 * ``useApplyTenantTheme`` in ``hooks/queries.ts`` for that wiring.
 *
 * The platform defaults are hardcoded here (mirroring ``index.css``) rather
 * than read from the live DOM. Reading the DOM at module load is fragile: the
 * brand override may already be applied as an inline style, and toggling the
 * ``.dark`` class just to measure causes a flash. The CSS values are stable
 * constants, so duplicating them is the simpler, flash-free contract. Keep
 * these in sync with ``src/index.css`` when the palette changes.
 */
const DEFAULT_PRIMARY_LIGHT = "221.2 83.2% 53.3%";
const DEFAULT_PRIMARY_FG_LIGHT = "210 40% 98%";
const DEFAULT_PRIMARY_DARK = "217.2 91.2% 59.8%";
const DEFAULT_PRIMARY_FG_DARK = "222.2 47.4% 11.2%";

/** True when the document is currently rendering in dark mode. */
export function isDarkMode(): boolean {
  if (typeof window === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}

/** Convert a ``#RRGGBB`` string to the shadcn HSL token format ``H S% L%``. */
export function hexToHsl(hex: string): string {
  const m = /^#([0-9a-fA-F]{6})$/.exec(hex.trim());
  if (!m) return DEFAULT_PRIMARY_LIGHT;
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

/** Contrast ratio between two ``#RRGGBB`` colors per WCAG (1–21). */
function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Pick the more readable foreground for a tenant color.
 *
 * Older code used a single luminance threshold (>0.45 → dark text), which
 * failed WCAG AA for saturated mid-tone brands (green/amber/orange got white
 * text at < 3:1). The correct approach: compute the contrast ratio against
 * BOTH near-black and near-white candidates and return whichever scores higher.
 * This guarantees the best attainable contrast for any brand color (P0-2).
 */
function bestForeground(hex: string): string {
  const dark = "#222222";
  const light = "#ffffff";
  return contrastRatio(hex, dark) >= contrastRatio(hex, light) ? dark : light;
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
 * (or an invalid value) restores the platform defaults for the *currently
 * active mode* (light or dark) — important because the platform's light and
 * dark primaries differ.
 *
 * The foreground contrast threshold (luminance > 0.45 picks near-black) is
 * mode-independent on purpose: ``--primary`` paints buttons / accents / links,
 * and the text sitting on it must contrast with the *tenant color itself*, not
 * with the page background. A red brand is red in light and dark mode alike,
 * so the same black-or-white text decision applies. (P0-2)
 */
export function applyThemeColor(hex: string | null | undefined): void {
  if (typeof window === "undefined") return;
  const root = document.documentElement;
  const dark = isDarkMode();
  if (!hex) {
    root.style.setProperty(
      "--primary",
      dark ? DEFAULT_PRIMARY_DARK : DEFAULT_PRIMARY_LIGHT,
    );
    root.style.setProperty(
      "--primary-foreground",
      dark ? DEFAULT_PRIMARY_FG_DARK : DEFAULT_PRIMARY_FG_LIGHT,
    );
    return;
  }
  root.style.setProperty("--primary", hexToHsl(hex));
  // Pick the foreground by maximizing WCAG contrast against the tenant color.
  // The near-black/near-white pair is the same family shadcn uses by default;
  // bestForeground returns a hex, converted to the HSL token format.
  root.style.setProperty("--primary-foreground", hexToHsl(bestForeground(hex)));
}
