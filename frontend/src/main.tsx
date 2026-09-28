import "@fontsource-variable/inter";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, homeFor, useAuth } from "./auth/AuthContext";
import { Layout, RoleGate } from "./components/Layout";
import { Batch } from "./pages/Batch";
import { Dashboard } from "./pages/Dashboard";
import { EsiaCallback } from "./pages/EsiaCallback";
import { EsiaMockLogin } from "./pages/EsiaMockLogin";
import { Login } from "./pages/Login";
import { Queue } from "./pages/Queue";
import { StudyDetail } from "./pages/StudyDetail";
import { Studies } from "./pages/Studies";
import { Upload } from "./pages/Upload";
import { Users } from "./pages/Users";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="min-h-[100dvh] grid place-items-center text-muted text-[15px]">Загружаем профиль</div>
    );
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function Home() {
  const { user } = useAuth();
  return <Navigate to={user ? homeFor(user.role) : "/login"} replace />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/auth/esia/callback" element={<EsiaCallback />} />
            <Route path="/esia-test/login" element={<EsiaMockLogin />} />
            <Route
              element={
                <Protected>
                  <Layout />
                </Protected>
              }
            >
              <Route index element={<Home />} />
              <Route path="/upload" element={<Upload />} />
              <Route path="/studies" element={<Studies />} />
              <Route path="/studies/:id" element={<StudyDetail />} />
              <Route
                path="/queue"
                element={
                  <RoleGate roles={["radiologist", "admin"]}>
                    <Queue />
                  </RoleGate>
                }
              />
              <Route
                path="/batch"
                element={
                  <RoleGate roles={["radiologist", "admin"]}>
                    <Batch />
                  </RoleGate>
                }
              />
              <Route
                path="/dashboard"
                element={
                  <RoleGate roles={["admin"]}>
                    <Dashboard />
                  </RoleGate>
                }
              />
              <Route
                path="/users"
                element={
                  <RoleGate roles={["admin"]}>
                    <Users />
                  </RoleGate>
                }
              />
            </Route>
            <Route path="*" element={<Home />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
