import tailwindcssTypography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        // Semantic status colors — success / warning / danger / info. Mirror the
        // destructive shape (DEFAULT + foreground). Danger coexists with the
        // legacy destructive name (shadcn/ui); danger is the semantic token for
        // business-page mapping. See index.css for the HSL source values.
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        danger: {
          DEFAULT: "hsl(var(--danger))",
          foreground: "hsl(var(--danger-foreground))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Sidebar — its own surface (nav panel). Consumed by the layout's
        // <aside> so the nav reads as a distinct panel from the main content.
        sidebar: {
          DEFAULT: "hsl(var(--sidebar))",
          foreground: "hsl(var(--sidebar-foreground))",
          border: "hsl(var(--sidebar-border))",
          accent: "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
        },
        // Chart palette — five hues for data viz (chart.tsx). Indexed 1..5 and
        // mapped to CSS vars that swap between light/dark automatically.
        chart: {
          1: "hsl(var(--chart-1))",
          2: "hsl(var(--chart-2))",
          3: "hsl(var(--chart-3))",
          4: "hsl(var(--chart-4))",
          5: "hsl(var(--chart-5))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      // Elevation semantics — two named layers so "which shadow for which
      // surface" is a concept, not an implicit convention. Both values are
      // character-for-character identical to Tailwind's defaults (shadow-sm /
      // shadow-lg), so mapping existing surfaces onto them is a zero-visual
      // change; the naming just makes the hierarchy explicit (Feature C 切片 01).
      //   - ``surface``: the content-card layer — a near-hairline shadow. Backs
      //     <Card> (default + glow). Equivalent to ``shadow-sm``. (Named
      //     ``surface``, not ``card``: a ``card`` key collides with the
      //     ``colors.card`` token — Tailwind emits a ``shadow-card`` *color*
      //     utility that shadows the size utility, turning the 5%-black drop
      //     into a solid-white one. See plan v1→v2 summary.)
      //   - ``overlay``: the floating layer — dialogs, dropdowns, selects,
      //     toasts. Lifts the surface above the page. Equivalent to
      //     ``shadow-lg``. (select/dropdown-content previously used shadow-md;
      //     unifying onto overlay lifts them to one consistent floating tier.)
      boxShadow: {
        surface: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        overlay: "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
      },
      // Animations — four CSS keyframe families backing the motion budget
      // (plan §6: most motion is CSS; motion lib is reserved for 4 specific
      // cases). These are utilities like `animate-fade-in`, `animate-shimmer`.
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-in-right": {
          from: { transform: "translateX(100%)" },
          to: { transform: "translateX(0)" },
        },
        "slide-in-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "slide-in-right": "slide-in-right 0.25s ease-out",
        "slide-in-up": "slide-in-up 0.25s ease-out",
        // Shimmer sweep for skeletons: a translucent gradient band that wipes
        // across the box. Pair with `relative overflow-hidden` + a `::before`.
        shimmer: "shimmer 1.5s infinite",
      },
    },
  },
  plugins: [tailwindcssTypography],
};
