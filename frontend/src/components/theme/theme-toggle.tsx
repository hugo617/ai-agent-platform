import { Moon, Sun, Laptop, Check } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useTheme, type Theme } from "@/components/theme/theme-provider";

/**
 * Top-bar theme switch — light / dark / system, persisted via ThemeProvider.
 *
 * Uses the existing dropdown primitive (no new Radix dep). The trigger icon
 * reflects the *resolved* theme (what's on screen), while the menu items set
 * the *preference*. ``aria-label`` keeps it usable for screen readers and for
 * the keyboard-shortcut crowd who'll reach it via the ⌘K command menu later.
 */

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "浅色", icon: Sun },
  { value: "dark", label: "深色", icon: Moon },
  { value: "system", label: "跟随系统", icon: Laptop },
];

export function ThemeToggle() {
  const { theme, resolvedTheme, setTheme } = useTheme();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="切换主题">
          {/* The visible icon tracks the applied theme, not the preference,
              so a ``system`` user still sees a sun/moon that matches reality.
              A small crossfade doubles as the P0-3 motion-on-React-19 probe. */}
          <AnimatePresence mode="wait" initial={false}>
            {resolvedTheme === "dark" ? (
              <motion.span
                key="moon"
                initial={{ opacity: 0, rotate: -30 }}
                animate={{ opacity: 1, rotate: 0 }}
                exit={{ opacity: 0, rotate: 30 }}
                transition={{ duration: 0.15 }}
              >
                <Moon className="h-5 w-5" />
              </motion.span>
            ) : (
              <motion.span
                key="sun"
                initial={{ opacity: 0, rotate: 30 }}
                animate={{ opacity: 1, rotate: 0 }}
                exit={{ opacity: 0, rotate: -30 }}
                transition={{ duration: 0.15 }}
              >
                <Sun className="h-5 w-5" />
              </motion.span>
            )}
          </AnimatePresence>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-36">
        {OPTIONS.map((opt) => (
          <DropdownMenuItem
            key={opt.value}
            onClick={() => setTheme(opt.value)}
            className="gap-2"
          >
            <opt.icon className="h-4 w-4" />
            <span className="flex-1">{opt.label}</span>
            <Check
              className={cn(
                "h-3.5 w-3.5",
                theme === opt.value ? "opacity-100" : "opacity-0",
              )}
            />
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
