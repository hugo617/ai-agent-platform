import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Bot,
  Building2,
  Contact,
  Coins,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  ScrollText,
  Settings,
  Shield,
  ShieldCheck,
  Store,
  UserCircle,
  Users,
  UserCog,
  Wallet,
  X,
} from "lucide-react";
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
import { canViewMenu, hasPermission } from "@/lib/permission";
import { logout } from "@/api/endpoints";
import { GlobalSearchBox } from "@/components/layout/global-search-box";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /**
   * The menu permission code that gates this item's visibility (e.g.
   * "menu:agents"). When set, the item shows iff `canViewMenu(me, menuCode)`.
   */
  menuCode?: string;
  /**
   * Platform-level items have no tenant-scoped menu permission (super_admin
   * bypass covers them); gate purely on platform_role === "super_admin".
   */
  platformOnly?: boolean;
  /**
   * Gate visibility on an api permission code (e.g. "wallet:read") instead of a
   * menu code. Used when a feature has no seeded menu permission but its api
   * permission is granted to the right roles. super_admin short-circuits true.
   */
  permission?: { obj: string; act: string };
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "概览", icon: LayoutDashboard, menuCode: "menu:dashboard" },
  { to: "/agents", label: "智能体", icon: Bot, menuCode: "menu:agents" },
  { to: "/chat", label: "对话", icon: MessageSquare, menuCode: "menu:chat" },
  { to: "/groups", label: "组织", icon: Building2, menuCode: "menu:groups" },
  { to: "/customers", label: "客户", icon: Contact, menuCode: "menu:customers" },
  // Token 费用管理系列 4/4 — store-level billing. No menu:billing permission is
  // seeded (the series ships wallet:read on owner/admin/member instead), so we
  // gate the nav item on the api permission directly. super_admin bypasses.
  {
    to: "/billing",
    label: "费用管理",
    icon: Wallet,
    permission: { obj: "wallet", act: "read" },
  },
  { to: "/tenants", label: "门店", icon: Store, platformOnly: true },
  // HQ-level billing — super_admin only (recharge + pricing policy).
  { to: "/billing/admin", label: "计费管理", icon: Coins, platformOnly: true },
  { to: "/members", label: "成员", icon: UserCog, menuCode: "menu:members" },
  { to: "/users", label: "用户", icon: Users, menuCode: "menu:users" },
  { to: "/roles", label: "角色", icon: Shield, menuCode: "menu:roles" },
  { to: "/permissions", label: "权限矩阵", icon: ShieldCheck, menuCode: "menu:permissions" },
  { to: "/settings", label: "设置", icon: Settings, menuCode: "menu:settings" },
  // 审计日志 — owner/admin see their store; super_admin/hq_staff see all.
  // No menu:logs permission is seeded, so gate on the api permission directly.
  {
    to: "/logs",
    label: "审计日志",
    icon: ScrollText,
    permission: { obj: "logs", act: "read" },
  },
];

export function DashboardLayout() {
  const { me, signOut } = useAuth();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(false);

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
      {/* Sidebar — fixed on desktop, drawer on mobile */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 border-r bg-background transition-transform lg:static lg:translate-x-0",
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 items-center gap-2 border-b px-6">
          <Shield className="h-6 w-6 text-primary" />
          <span className="text-lg font-semibold">智能体云平台</span>
        </div>
        <nav className="flex flex-col gap-1 p-4">
          {NAV_ITEMS.filter((item) => {
            // Platform-level items (e.g. /tenants, /billing/admin) have no
            // tenant menu perm — show them purely on platform_role.
            if (item.platformOnly) return me?.platform_role === "super_admin";
            // Api-permission-gated items (e.g. /billing on wallet:read).
            if (item.permission)
              return hasPermission(
                me,
                item.permission.obj,
                item.permission.act,
              );
            // Otherwise visibility is driven by the menu permission code.
            return canViewMenu(me, item.menuCode ?? "");
          }).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main column */}
      <div className="flex flex-1 flex-col">
        <header className="flex h-16 items-center justify-between border-b bg-background px-4 lg:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen((v) => !v)}
          >
            {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </Button>
          {/* 全局搜索框 — top-bar cross-entity search (priority 51). Hidden on
              small screens (the mobile hamburger takes the space); the flexible
              spacer keeps the right-side badges pinned to the edge. */}
          <div className="hidden flex-1 justify-center px-4 sm:flex">
            <GlobalSearchBox />
          </div>
          <div className="flex items-center gap-3">
            {me?.platform_role === "super_admin" && (
              <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100 border-amber-300">
                🛡️ 超级管理员
              </Badge>
            )}
            {me?.roles?.[0] && (
              <Badge variant="secondary">{me.roles[0]}</Badge>
            )}
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
    </div>
  );
}
