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
import { DashboardLayout } from "@/components/layout/dashboard-layout";
import { LoginPage } from "@/pages/login-page";
import { DashboardPage } from "@/pages/dashboard-page";
import { AgentsPage } from "@/pages/agents-page";
import { ChatPage } from "@/pages/chat-page";
import { GroupsPage } from "@/pages/groups-page";
import { CustomersPage } from "@/pages/customers-page";
import { RolesPage } from "@/pages/roles-page";
import { MembersPage } from "@/pages/members-page";
import { PermissionsPage } from "@/pages/permissions-page";
import { SettingsPage } from "@/pages/settings-page";
import { TenantsPage } from "@/pages/tenants-page";
import { UsersPage } from "@/pages/users-page";
import { NotFoundPage } from "@/pages/not-found-page";
import { BillingPage } from "@/pages/billing-page";
import { BillingAdminPage } from "@/pages/billing-admin-page";
import { LogsPage } from "@/pages/logs-page";

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
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
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
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
