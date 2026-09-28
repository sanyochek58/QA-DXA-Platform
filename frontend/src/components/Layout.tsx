import {
  Archive,
  ChartPieSlice,
  Files,
  PlusCircle,
  SignOut,
  Stethoscope,
  UsersThree,
  type Icon,
} from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { Role, StudyPage, SystemStatus } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ROLE_LABEL } from "../lib/format";
import { Avatar } from "./ui";

interface NavItem {
  to: string;
  label: string;
  short: string; // подпись в таб-баре: одно слово
  icon: Icon;
  roles: Role[];
  badge?: number;
  inTabBar?: boolean; // в таб-баре iOS не больше 5 вкладок
}

/** Иконка приложения: четыре позвонка на фирменном синем. */
export function AppIcon({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <rect width="32" height="32" rx="7.5" fill="#1565c0" />
      <g fill="#fff">
        <rect x="11" y="5" width="10" height="4.2" rx="1.6" />
        <rect x="10.5" y="10.6" width="11" height="4.4" rx="1.6" />
        <rect x="10" y="16.4" width="12" height="4.6" rx="1.6" />
        <rect x="9.5" y="22.4" width="13" height="4.8" rx="1.6" />
      </g>
    </svg>
  );
}

function SystemStatusLine() {
  const { data } = useQuery({
    queryKey: ["system"],
    queryFn: () => api<SystemStatus>("/system/status"),
    refetchInterval: 30_000,
  });
  if (!data || (data.database === "ok" && data.ml === "ok")) return null;
  return (
    <div role="status" className="mb-6 rounded-2xl bg-warn-soft text-warn text-[14px] px-4 py-3">
      {data.ml !== "ok"
        ? "Сервис анализа недоступен. Новые исследования сохранятся, проверка начнётся после восстановления."
        : "База данных недоступна. Обратитесь к администратору."}
    </div>
  );
}

function useNav(): NavItem[] {
  const { user } = useAuth();
  const queue = useQuery({
    queryKey: ["queue-count"],
    queryFn: () => api<StudyPage>("/studies/queue"),
    enabled: !!user && user.role !== "technologist",
    refetchInterval: 20_000,
  });
  if (!user) return [];
  const all: NavItem[] = [
    { to: "/dashboard", label: "Сводка", short: "Сводка", icon: ChartPieSlice, roles: ["admin"] },
    { to: "/upload", label: "Новое исследование", short: "Загрузить", icon: PlusCircle, roles: ["technologist", "radiologist", "admin"] },
    { to: "/queue", label: "На проверку", short: "Проверка", icon: Stethoscope, roles: ["radiologist", "admin"], badge: queue.data?.total },
    { to: "/studies", label: "Исследования", short: "Архив", icon: Files, roles: ["technologist", "radiologist", "admin"] },
    { to: "/batch", label: "Пакетная проверка", short: "Пакет", icon: Archive, roles: ["radiologist", "admin"], inTabBar: false },
    { to: "/users", label: "Сотрудники", short: "Сотрудники", icon: UsersThree, roles: ["admin"] },
  ];
  return all.filter((i) => i.roles.includes(user.role));
}

function Sidebar({ items }: { items: NavItem[] }) {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <aside className="hidden lg:flex fixed inset-y-0 left-0 w-[264px] flex-col bg-surface/80 backdrop-blur-xl border-r border-line z-30">
      <div className="flex items-center gap-3 px-6 h-20">
        <AppIcon size={34} />
        <div className="leading-tight">
          <div className="text-[17px] font-semibold tracking-[-0.01em]">Остеоконтроль</div>
          <div className="text-[13px] text-muted">Денситометрия</div>
        </div>
      </div>
      <nav className="flex-1 px-3 flex flex-col gap-0.5" aria-label="Разделы">
        {items.map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            className={({ isActive }) =>
              `flex items-center gap-3 h-11 px-3 rounded-xl text-[15px] transition-colors ${
                isActive ? "bg-brand-soft text-brand font-semibold" : "text-ink hover:bg-fill"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <i.icon size={22} weight={isActive ? "fill" : "regular"} className={isActive ? "" : "text-brand"} />
                <span className="flex-1">{i.label}</span>
                {!!i.badge && (
                  <span className="min-w-6 h-6 px-1.5 rounded-full bg-bad-fill text-white text-[13px] font-semibold grid place-items-center tnum">
                    {i.badge}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="m-3 p-3 rounded-2xl bg-fill flex items-center gap-3">
        <Avatar name={user.full_name} />
        <div className="flex-1 min-w-0 leading-tight">
          <div className="text-[14px] font-semibold truncate">{user.full_name}</div>
          <div className="text-[13px] text-muted truncate">{ROLE_LABEL[user.role]}</div>
        </div>
        <button onClick={logout} className="size-9 grid place-items-center rounded-full text-muted hover:bg-fill-2 hover:text-ink" aria-label="Выйти" title="Выйти">
          <SignOut size={20} />
        </button>
      </div>
    </aside>
  );
}

function MobileTopBar() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <header className="lg:hidden sticky top-0 z-30 bg-paper/80 backdrop-blur-xl">
      <div className="flex items-center gap-2.5 px-4 h-14">
        <AppIcon size={28} />
        <span className="text-[16px] font-semibold flex-1">Остеоконтроль</span>
        <button onClick={logout} className="flex items-center gap-2 h-9 pl-1 pr-3 rounded-full hover:bg-fill-2" aria-label={`Выйти (${user.full_name})`}>
          <Avatar name={user.full_name} size={30} />
          <SignOut size={18} className="text-muted" />
        </button>
      </div>
    </header>
  );
}

function TabBar({ items }: { items: NavItem[] }) {
  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 z-30 bg-surface/85 backdrop-blur-xl border-t border-line"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      aria-label="Разделы"
    >
      <div className="flex">
        {items.map((i) => (
          <NavLink
            key={i.to}
            to={i.to}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center justify-center gap-0.5 h-[56px] text-[11px] font-medium ${
                isActive ? "text-brand" : "text-muted"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className="relative">
                  <i.icon size={25} weight={isActive ? "fill" : "regular"} />
                  {!!i.badge && (
                    <span className="absolute -top-1 -right-2.5 min-w-[18px] h-[18px] px-1 rounded-full bg-bad-fill text-white text-[11px] font-semibold grid place-items-center tnum">
                      {i.badge}
                    </span>
                  )}
                </span>
                {i.short}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

export function Layout() {
  const { user } = useAuth();
  const items = useNav();
  const { pathname } = useLocation();
  if (!user) return null;
  return (
    <div className="min-h-[100dvh]">
      <Sidebar items={items} />
      <MobileTopBar />
      <main className="lg:pl-[264px] pb-[calc(76px+env(safe-area-inset-bottom))] lg:pb-0">
        <div key={pathname} className="page-in max-w-[1180px] mx-auto px-4 md:px-8 lg:px-10 pt-4 md:pt-8 lg:pt-12 pb-10">
          <SystemStatusLine />
          <Outlet />
        </div>
      </main>
      <TabBar items={items.filter((i) => i.inTabBar !== false)} />
    </div>
  );
}

export function RoleGate({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth();
  if (!user || !roles.includes(user.role))
    return <div className="card p-8 text-center text-[15px] text-muted">Раздел недоступен для вашей роли.</div>;
  return <>{children}</>;
}
