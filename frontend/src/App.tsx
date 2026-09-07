import { Navigate, RouterProvider, createBrowserRouter } from "react-router-dom";

import { DashboardLayout } from "@/layouts/DashboardLayout";
import { ProtectedRoute } from "@/components/common/ProtectedRoute";
import { AuthProvider } from "@/context/AuthContext";
import { ThemeProvider } from "@/context/ThemeContext";
import { AdminPage } from "@/pages/Admin";
import { AIPage } from "@/pages/AI";
import { AlertsPage } from "@/pages/Alerts";
import { AuthCallbackPage } from "@/pages/Auth/AuthCallbackPage";
import { DashboardPage } from "@/pages/Dashboard";
import { EventsPage } from "@/pages/Events";
import { IncidentsPage } from "@/pages/Incidents";
import { KubernetesPage } from "@/pages/Kubernetes";
import { LoginPage } from "@/pages/Auth/LoginPage";
import { LogsPage } from "@/pages/Logs";
import { MetricsPage } from "@/pages/Metrics";
import { ReportsPage } from "@/pages/Reports";
import { SettingsPage } from "@/pages/Settings";
import { TerminalPage } from "@/pages/Terminal";
import { TracesPage } from "@/pages/Traces";

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/auth/callback",
    element: <AuthCallbackPage />,
  },
  {
    path: "/",
    element: (
      <ProtectedRoute>
        <DashboardLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "dashboard", element: <Navigate to="/" replace /> },
      { path: "kubernetes", element: <KubernetesPage /> },
      { path: "metrics", element: <MetricsPage /> },
      { path: "logs", element: <LogsPage /> },
      { path: "traces", element: <TracesPage /> },
      { path: "events", element: <EventsPage /> },
      { path: "alerts", element: <AlertsPage /> },
      { path: "incidents", element: <IncidentsPage /> },
      { path: "ai", element: <AIPage /> },
      { path: "reports", element: <ReportsPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "terminal", element: <TerminalPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  );
}
