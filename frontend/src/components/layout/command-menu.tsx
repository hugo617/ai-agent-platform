import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Command } from "cmdk";
import {
  Bot,
  Building2,
  Contact,
  Laptop,
  LogOut,
  Moon,
  Search,
  Sun,
  UserCircle,
} from "lucide-react";
import { useAuth } from "@/components/auth/auth-context";
import { useTheme } from "@/components/theme/theme-provider";
import { useGlobalSearch } from "@/hooks/queries";
import { logout } from "@/api/endpoints";
import { visibleGroups } from "@/components/layout/nav-items";
import { cn } from "@/lib/utils";

/**
 * ⌘K / Ctrl+K command palette (Linear-style).
 *
 * Three sections:
 *   1. **导航** — every route the user may visit (reuses ``visibleGroups``, the
 *      same model the sidebar uses), filtered by the current query.
 *   2. **搜索** — once the query is ≥ 2 chars, cross-entity hits from
 *      ``useGlobalSearch`` (agents / customers / conversations / users /
 *      tenants), top 5 each. Selecting a hit navigates to its page.
 *   3. **快捷操作** — toggle theme (light/dark/system) + sign out.
 *
 * Filtering: cmdk's built-in fuzzy filter handles the 导航 + 快捷操作 groups.
 * For 搜索 we set ``shouldFilter={false}`` on the outer Command and gate the
 * search group on the query length ourselves — the backend already returns
 * ranked results, so double-filtering would drop good hits.
 *
 * The palette is mounted once in ``DashboardLayout`` and toggled by a global
 * ⌘K/Ctrl+K listener (see ``useOpenOnCmdK`` below). It is keyboard-first: type
 * to filter, ↑↓ to move, Enter to run, Esc to close.
 */

// Category metadata for search hits — mirrors global-search-box.tsx so the two
// entry points behave identically.
const SEARCH_CATEGORIES = {
  agents: { label: "智能体", icon: Bot, route: "/agents" },
  customers: { label: "客户", icon: Contact, route: "/customers" },
  conversations: { label: "对话", icon: Search, route: "/chat" },
  users: { label: "用户", icon: UserCircle, route: "/users" },
  tenants: { label: "门店", icon: Building2, route: "/tenants" },
} as const;

type SearchKey = keyof typeof SEARCH_CATEGORIES;

/** Global ⌘K / Ctrl+K listener — call once at the layout root. */
export function useOpenOnCmdK(onOpen: (open: boolean) => void) {
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpen(true);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onOpen]);
}

export function CommandMenu({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { me, signOut } = useAuth();
  const { setTheme } = useTheme();
  const navigate = useNavigate();
  const [search, setSearch] = React.useState("");

  // Cross-entity search — only fires for terms ≥ 2 chars (useGlobalSearch gates
  // the request). Disabled while the palette is closed to avoid stray requests.
  const debounced = search.trim();
  const { data: searchResults, isFetching } = useGlobalSearch(debounced);
  const showSearch = debounced.length >= 2 && open;
  const groups = visibleGroups(me);

  const close = React.useCallback(() => {
    onOpenChange(false);
    setSearch("");
  }, [onOpenChange]);

  const run = React.useCallback(
    (fn: () => void) => {
      fn();
      close();
    },
    [close],
  );

  const handleSignOut = React.useCallback(async () => {
    try {
      await logout();
    } catch {
      // 401 expected if the token already expired.
    }
    signOut();
    navigate("/login", { replace: true });
  }, [signOut, navigate]);

  return (
    <Command.Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setSearch("");
      }}
      label="命令菜单"
      // Don't let cmdk fuzzy-filter the search group — the backend already
      // ranked results and re-filtering would drop good hits. We gate the
      // search group on query length ourselves below.
      shouldFilter={search.length < 2}
      overlayClassName="fixed inset-0 z-[100] bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
      contentClassName="fixed left-[50%] top-[20%] z-[100] w-full max-w-xl -translate-x-1/2 overflow-hidden rounded-lg border bg-popover shadow-lg"
    >
      {/* Input */}
      <div className="flex items-center border-b px-3">
        <Search className="mr-2 h-4 w-4 shrink-0 text-muted-foreground" />
        <Command.Input
          value={search}
          onValueChange={setSearch}
          placeholder="搜索或输入命令…"
          className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        <kbd className="ml-2 hidden shrink-0 rounded border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground sm:inline">
          ESC
        </kbd>
      </div>

      <Command.List className="max-h-[60vh] overflow-y-auto p-2">
        <Command.Empty>
          {isFetching ? "搜索中…" : "无匹配结果"}
        </Command.Empty>

        {/* 1. 导航 — only show when not actively searching the backend. */}
        {!showSearch &&
          groups.map((group) => (
            <Command.Group
              key={group.label}
              heading={group.label}
              className="overflow-hidden p-1 text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium"
            >
              {group.items.map((item) => (
                <Command.Item
                  key={item.to}
                  value={`${item.label} ${group.label}`}
                  onSelect={() => run(() => navigate(item.to))}
                  className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </Command.Item>
              ))}
            </Command.Group>
          ))}

        {/* 2. 搜索 — cross-entity hits. */}
        {showSearch &&
          (Object.keys(SEARCH_CATEGORIES) as SearchKey[])
            .filter((key) => (searchResults?.[key]?.length ?? 0) > 0)
            .map((key) => {
              const cfg = SEARCH_CATEGORIES[key];
              const items = searchResults?.[key] ?? [];
              return (
                <Command.Group
                  key={key}
                  heading={cfg.label}
                  className="overflow-hidden p-1 text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium"
                >
                  {items.map((hit) => (
                    <Command.Item
                      key={`${key}-${hit.id}`}
                      value={hit.label}
                      onSelect={() => run(() => navigate(cfg.route))}
                      className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
                    >
                      <cfg.icon className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <span className="truncate">{hit.label}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              );
            })}

        {/* 3. 快捷操作 */}
        {!showSearch && (
          <Command.Group
            heading="快捷操作"
            className="overflow-hidden p-1 text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium"
          >
            <Command.Item
              value="浅色 light"
              onSelect={() => run(() => setTheme("light"))}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
            >
              <Sun className="h-4 w-4" />
              <span>切换到浅色主题</span>
            </Command.Item>
            <Command.Item
              value="深色 dark"
              onSelect={() => run(() => setTheme("dark"))}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
            >
              <Moon className="h-4 w-4" />
              <span>切换到深色主题</span>
            </Command.Item>
            <Command.Item
              value="跟随系统 system"
              onSelect={() => run(() => setTheme("system"))}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground"
            >
              <Laptop className="h-4 w-4" />
              <span>主题跟随系统</span>
            </Command.Item>
            <Command.Item
              value="退出登录 signout logout"
              onSelect={() => run(() => void handleSignOut())}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm",
                "data-[selected=true]:bg-destructive/10 data-[selected=true]:text-destructive",
              )}
            >
              <LogOut className="h-4 w-4" />
              <span>退出登录</span>
            </Command.Item>
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  );
}
