import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Bot,
  Building2,
  Contact,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Settings,
  Shield,
  ShieldCheck,
  Store,
  Users,
  UserCog,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/components/auth/auth-context";
import { canManageUsers } from "@/lib/permission";
import { logout } from "@/api/endpoints";

interface NavItem {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** When true, the item is hidden for users who can't manage users (members). */
  needsUserManagement?: boolean;
  /** When true, the item is visible only to platform super admins. */
  needsSuperAdmin?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "概览", icon: LayoutDashboard },
  { to: "/agents", label: "智能体", icon: Bot },
  { to: "/chat", label: "对话", icon: MessageSquare },
  { to: "/groups", label: "组织", icon: Building2 },
  { to: "/customers", label: "客户", icon: Contact },
  { to: "/tenants", label: "门店", icon: Store, needsSuperAdmin: true },
  { to: "/members", label: "成员", icon: UserCog, needsUserManagement: true },
  { to: "/users", label: "用户", icon: Users, needsUserManagement: true },
  { to: "/roles", label: "角色", icon: Shield, needsUserManagement: true },
  { to: "/permissions", label: "权限矩阵", icon: ShieldCheck, needsUserManagement: true },
  { to: "/settings", label: "设置", icon: Settings, needsUserManagement: true },
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
            if (item.needsSuperAdmin) return me?.platform_role === "super_admin";
            if (item.needsUserManagement) return canManageUsers(me);
            return true;
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
          <div className="flex-1" />
          <div className="flex items-center gap-3">
            {me?.platform_role === "super_admin" && (
              <Badge className="bg-amber-100 text-amber-800 hover:bg-amber-100 border-amber-300">
                🛡️ 超级管理员
              </Badge>
            )}
            {me?.roles?.[0] && (
              <Badge variant="secondary">{me.roles[0]}</Badge>
            )}
            <span className="text-sm text-muted-foreground">
              {me?.email ?? me?.user_id}
            </span>
            <Button variant="ghost" size="icon" onClick={handleSignOut} title="退出登录">
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
