import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { LogOut, Menu, Shield, UserCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/components/auth/auth-context";
import { isSuperAdmin } from "@/lib/permission";
import { logout } from "@/api/endpoints";
import { GlobalSearchBox } from "@/components/layout/global-search-box";
import { NotificationBell } from "@/components/layout/notification-bell";
import { ThemeToggle } from "@/components/theme/theme-toggle";
import { SecureImage } from "@/components/ui/secure-image";
import {
  CommandMenu,
  useOpenOnCmdK,
} from "@/components/layout/command-menu";
import { visibleGroups } from "@/components/layout/nav-items";
import { useApplyTenantTheme, useTenantConfig } from "@/hooks/queries";

/**
 * Application shell — grouped sidebar + top bar + command palette.
 *
 * Sidebar (§1.1): the flat 16-item nav is grouped into three sections
 * (工作台 / 管理 / 平台) via ``visibleGroups``, each permission-filtered. A user
 * card (avatar + name + tenant + sign-out) pins to the bottom. On mobile the
 * sidebar becomes a drawer animated with ``motion`` (§1.1) — AnimatePresence
 * handles the enter/exit sweep.
 *
 * Top bar (§1.2): hamburger (mobile) + ⌘K trigger (with the shortcut hint) on
 * the left; the cross-entity search box fills the center; ThemeToggle +
 * NotificationBell + super-admin badge + role badge + user dropdown on the
 * right. The ⌘K command palette (§1.3) is mounted here and toggled by a global
 * keydown listener.
 */

export function DashboardLayout() {
  const { me, signOut } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  // ⌘K / Ctrl+K toggles the command palette from anywhere.
  useOpenOnCmdK(setCommandOpen);

  // Tenant white-label branding (priority 52): apply the theme color globally
  // and surface the display name + logo in the sidebar header. The theme effect
  // restores the platform default on logout/tenant switch via its cleanup.
  const { data: tenantConfig } = useTenantConfig();
  useApplyTenantTheme();
  const brandName = tenantConfig?.display_name ?? "智能体云平台";
  const brandLogo = tenantConfig?.logo_url;

  const groups = visibleGroups(me);

  const handleSignOut = async () => {
    // Ask the backend to revoke the session row (best-effort: a network error
    // must not strand the user in a logged-in UI). Local state is cleared after.
    try {
      await logout();
    } catch {
      // 401 is expected if the token already expired; ignore either way.
    }
    signOut();
    navigate("/login", { replace: true });
  };

  return (
    <div className="flex min-h-screen bg-muted/20">
      {/* Sidebar — fixed on desktop (always visible), drawer on mobile */}
      <Sidebar
        groups={groups}
        brandName={brandName}
        brandLogo={brandLogo}
        me={me}
        onNavigate={() => setSidebarOpen(false)}
        onSignOut={handleSignOut}
      />

      {/* Mobile drawer — motion-animated sweep (§1.1). AnimatePresence drives
          the exit so the drawer glides out instead of vanishing. */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              key="overlay"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="fixed inset-0 z-40 bg-black/40 lg:hidden"
              onClick={() => setSidebarOpen(false)}
            />
            <motion.aside
              key="drawer"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "tween", duration: 0.25, ease: "easeOut" }}
              className="fixed inset-y-0 left-0 z-50 w-64 lg:hidden"
            >
              <Sidebar
                groups={groups}
                brandName={brandName}
                brandLogo={brandLogo}
                me={me}
                onNavigate={() => setSidebarOpen(false)}
                onSignOut={handleSignOut}
                embedded
              />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* Main column */}
      <div className="flex flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between gap-2 border-b bg-background/80 px-4 backdrop-blur lg:px-6">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label="切换侧边栏"
            >
              {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
            {/* ⌘K trigger — shows the shortcut hint; the real listener is global. */}
            <Button
              variant="outline"
              size="sm"
              className="hidden gap-2 text-muted-foreground sm:flex"
              onClick={() => setCommandOpen(true)}
            >
              <span>搜索或命令…</span>
              <kbd className="rounded border bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                ⌘K
              </kbd>
            </Button>
          </div>

          {/* 全局搜索框 — top-bar cross-entity search (priority 51). Hidden on
              small screens (the ⌘K palette + hamburger take the space). */}
          <div className="hidden flex-1 justify-center px-4 md:flex">
            <GlobalSearchBox />
          </div>

          <div className="flex items-center gap-3">
            {/* 主题切换(亮/暗/跟随系统) — 持久化在 localStorage,由 ThemeProvider
                管理 .dark 类。放通知铃铛前,顶栏右侧。 */}
            <ThemeToggle />
            {/* 通知铃铛(priority 54) — 未读数 badge + 下拉。Every authenticated
                user reads their own notifications, so no permission guard. */}
            <NotificationBell />
            {isSuperAdmin(me) && (
              <Badge className="border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-100">
                🛡️ 超级管理员
              </Badge>
            )}
            {me?.roles?.[0] && <Badge variant="secondary">{me.roles[0]}</Badge>}
            {/* 用户菜单 — 头像下拉：「个人中心」+「退出登录」。Every
                authenticated user can reach their own profile, so no permission
                guard on the entry. */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="gap-2">
                  <UserCircle className="h-5 w-5" />
                  <span className="max-w-[12rem] truncate text-sm">
                    {me?.email ?? me?.user_id}
                  </span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuLabel className="truncate">
                  {me?.email ?? me?.user_id}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/profile")}>
                  <UserCircle className="mr-2 h-4 w-4" />
                  个人中心
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleSignOut}>
                  <LogOut className="mr-2 h-4 w-4" />
                  退出登录
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>

      {/* ⌘K command palette (§1.3) — mounted once, toggled globally. */}
      <CommandMenu open={commandOpen} onOpenChange={setCommandOpen} />
    </div>
  );
}

/**
 * The sidebar surface itself. Rendered twice: as the static desktop rail (in
 * normal flow, ``embedded=false`` so it's ``fixed``) and as the mobile drawer's
 * content (``embedded=true``, positioned by the parent motion.aside).
 *
 * Keeping one component means the brand header, nav groups, and user card stay
 * identical between the two — no drift.
 */
function Sidebar({
  groups,
  brandName,
  brandLogo,
  me,
  onNavigate,
  onSignOut,
  embedded = false,
}: {
  groups: ReturnType<typeof visibleGroups>;
  brandName: string;
  brandLogo?: string | null;
  me: ReturnType<typeof useAuth>["me"];
  onNavigate: () => void;
  onSignOut: () => void;
  embedded?: boolean;
}) {
  return (
    <aside
      className={cn(
        "flex flex-col border-r bg-sidebar text-sidebar-foreground",
        embedded
          ? "h-full w-full"
          : "fixed inset-y-0 left-0 z-40 w-64 lg:static lg:translate-x-0",
      )}
    >
      {/* Brand header */}
      <div className="flex h-16 shrink-0 items-center gap-2 border-b border-sidebar-border px-6">
        {brandLogo ? (
          <SecureImage
            src={brandLogo}
            alt={brandName}
            className="h-7 w-7 shrink-0 rounded object-contain"
          />
        ) : (
          <Shield className="h-6 w-6 text-primary" />
        )}
        <span className="truncate text-lg font-semibold">{brandName}</span>
      </div>

      {/* Grouped nav */}
      <nav className="flex-1 space-y-4 overflow-y-auto p-3">
        {groups.map((group) => (
          <div key={group.label}>
            <div className="px-3 py-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
              {group.label}
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      {/* User card pinned to the bottom */}
      <div className="shrink-0 border-t border-sidebar-border p-3">
        <div className="flex items-center gap-2 rounded-md px-2 py-2">
          <UserCircle className="h-8 w-8 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">
              {me?.email ?? me?.user_id}
            </div>
            {me?.roles?.[0] && (
              <div className="truncate text-xs text-muted-foreground">
                {me.roles[0]}
              </div>
            )}
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={onSignOut}
            aria-label="退出登录"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </aside>
  );
}
