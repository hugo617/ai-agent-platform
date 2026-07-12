import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/components/auth/auth-context";
import { ProtectedRoute } from "@/components/auth/protected-route";
import { RequireUserManagement } from "@/components/auth/require-permission";
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
import { UsersPage } from "@/pages/users-page";
import { NotFoundPage } from "@/pages/not-found-page";

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
