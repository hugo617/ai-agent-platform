import { lazy, Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/components/auth/auth-context";
import { ProtectedRoute } from "@/components/auth/protected-route";
import {
  RequireApiPermission,
  RequireUserManagement,
} from "@/components/auth/require-permission";
import { RequireSuperAdmin } from "@/components/auth/require-super-admin";
import { ToastProvider } from "@/components/ui/toast";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { LoginPage } from "@/pages/login-page";

// Code-splitting: every authenticated page is lazy-loaded so the initial
// bundle (login screen) only carries auth + layout, and each route's code is
// fetched on demand. Pages use named exports, so the `.then(m => ({default:
// m.X}))` shim adapts them to React.lazy's default-export expectation.
// LoginPage stays eager — it's the first thing unauthenticated users see.
const DashboardPage = lazy(() =>
  import("@/pages/dashboard-page").then((m) => ({ default: m.DashboardPage })),
);
const AgentsPage = lazy(() =>
  import("@/pages/agents-page").then((m) => ({ default: m.AgentsPage })),
);
const ChatPage = lazy(() =>
  import("@/pages/chat-page").then((m) => ({ default: m.ChatPage })),
);
const GroupsPage = lazy(() =>
  import("@/pages/groups-page").then((m) => ({ default: m.GroupsPage })),
);
const CustomersPage = lazy(() =>
  import("@/pages/customers-page").then((m) => ({ default: m.CustomersPage })),
);
const DevicesPage = lazy(() =>
  import("@/pages/devices-page").then((m) => ({ default: m.DevicesPage })),
);
const BookingsPage = lazy(() =>
  import("@/pages/bookings/bookings-page").then((m) => ({ default: m.BookingsPage })),
);
const RolesPage = lazy(() =>
  import("@/pages/roles-page").then((m) => ({ default: m.RolesPage })),
);
const MembersPage = lazy(() =>
  import("@/pages/members-page").then((m) => ({ default: m.MembersPage })),
);
const PermissionsPage = lazy(() =>
  import("@/pages/permissions-page").then((m) => ({ default: m.PermissionsPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings-page").then((m) => ({ default: m.SettingsPage })),
);
const TenantsPage = lazy(() =>
  import("@/pages/tenants-page").then((m) => ({ default: m.TenantsPage })),
);
const UsersPage = lazy(() =>
  import("@/pages/users-page").then((m) => ({ default: m.UsersPage })),
);
const ProfilePage = lazy(() =>
  import("@/pages/profile-page").then((m) => ({ default: m.ProfilePage })),
);
const NotFoundPage = lazy(() =>
  import("@/pages/not-found-page").then((m) => ({ default: m.NotFoundPage })),
);
const BillingPage = lazy(() =>
  import("@/pages/billing-page").then((m) => ({ default: m.BillingPage })),
);
const BillingAdminPage = lazy(() =>
  import("@/pages/billing-admin-page").then((m) => ({ default: m.BillingAdminPage })),
);
const LogsPage = lazy(() =>
  import("@/pages/logs-page").then((m) => ({ default: m.LogsPage })),
);
const NotificationsPage = lazy(() =>
  import("@/pages/notifications-page").then((m) => ({ default: m.NotificationsPage })),
);
const KnowledgePage = lazy(() =>
  import("@/pages/knowledge-page").then((m) => ({ default: m.KnowledgePage })),
);

/** Full-screen spinner shown while a lazy route chunk loads. */
function RouteFallback() {
  return (
    <div className="flex h-[50vh] items-center justify-center text-muted-foreground">
      <span className="text-sm">加载中…</span>
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <Suspense fallback={<RouteFallback />}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />

              {/* All routes below require authentication */}
              <Route
                element={
                  <ProtectedRoute>
                    <DashboardLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/" element={<DashboardPage />} />
                <Route path="/agents" element={<AgentsPage />} />
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/groups" element={<GroupsPage />} />
                <Route path="/customers" element={<CustomersPage />} />
                {/* 设备实例管理(devices-crud-ui 系列 2/4)— 门店 CRUD +
                    HQ 全景。member 可读(后端 devices:read 默认授予),
                    所以裸 ProtectedRoute,无额外守卫;写按钮在页内按
                    hasPermission 隐藏(切片 06)。 */}
                <Route path="/devices" element={<DevicesPage />} />
                {/* 设备预约订单(device-booking 系列 3/4 切片 05)— 切片 05 只铺
                    地基:types/endpoints/queries + 本路由 + nav 项,页面暂为
                    占位(无 UI)。member 可读(后端 bookings:read 切片 02 已 seed
                    给 owner/admin/member),所以裸 ProtectedRoute,无额外守卫;
                    写按钮 + 三叉视图(Store/HQ/customer)留给切片 06/07。 */}
                <Route path="/bookings" element={<BookingsPage />} />
                <Route path="/knowledge" element={<KnowledgePage />} />

                {/* 个人中心 — self-service account management. Every
                    authenticated user manages their own profile, so no
                    permission guard (beyond ProtectedRoute) is needed. */}
                <Route path="/profile" element={<ProfilePage />} />

                {/* 通知中心(priority 54) — in-app notifications. Every
                    authenticated user reads their own notifications; the
                    backend scopes by user_id + tenant_id. */}
                <Route path="/notifications" element={<NotificationsPage />} />

                {/* Token 费用管理系列 4/4 — store-level billing dashboard.
                    Gated on wallet:read (seeded to owner/admin/member). The HQ
                    admin route is super_admin only. */}
                <Route element={<RequireApiPermission />}>
                  <Route path="/billing" element={<BillingPage />} />
                  {/* 审计日志 — gated on logs:read (seeded to owner/admin).
                      super_admin/hq_staff see cross-tenant rows. */}
                  <Route path="/logs" element={<LogsPage />} />
                </Route>

                {/* Platform-level (super_admin only) routes. The backend still
                    enforces 403 on GET /tenants/all for non-super-admins; this
                    guard is a UX layer that keeps the nav item and route out
                    of reach for tenant users. */}
                <Route element={<RequireSuperAdmin />}>
                  <Route path="/tenants" element={<TenantsPage />} />
                  <Route path="/billing/admin" element={<BillingAdminPage />} />
                </Route>

                {/* User-management routes also require authorization: a plain
                    member is redirected to "/". The backend still enforces 403
                    as the hard boundary; this guard is a UX layer. */}
                <Route element={<RequireUserManagement />}>
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="/roles" element={<RolesPage />} />
                  <Route path="/permissions" element={<PermissionsPage />} />
                  <Route path="/members" element={<MembersPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Route>

              <Route path="*" element={<NotFoundPage />} />
              <Route path="/404" element={<NotFoundPage />} />
            </Routes>
            </Suspense>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
