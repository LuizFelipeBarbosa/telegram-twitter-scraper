import { clsx } from "clsx";
import { NavLink, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

interface RouteEntry {
  label: string;
  path?: string;
  disabled?: boolean;
  detailOnly?: boolean;
}

const ROUTES: RouteEntry[] = [
  { label: "Landscape", path: "/" },
  { label: "Node Detail", detailOnly: true },
  { label: "Trends", disabled: true },
  { label: "Propagation", disabled: true },
  { label: "Evolution", disabled: true },
];

interface NavItemProps {
  to: string;
  active: boolean;
  end?: boolean;
  children: ReactNode;
}

function NavItem({ to, active, end, children }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={end}
      data-active={active ? "true" : "false"}
      className={clsx(
        "relative pb-[0.3rem]",
        active &&
          "font-semibold after:content-[''] after:absolute after:inset-x-0 after:-bottom-[0.75rem] after:h-[2px] after:bg-phase-emerging",
      )}
    >
      {children}
    </NavLink>
  );
}

export function TopNav() {
  const location = useLocation();
  const onDetail = location.pathname.startsWith("/node/");
  const onRoot = location.pathname === "/";

  return (
    <header className="border-b border-ink bg-paper">
      <div className="flex items-center justify-between px-5 py-3 gap-6">
        <div className="flex flex-col">
          <span className="font-display text-[1.05rem] font-medium leading-none tracking-tight">
            Telegram Knowledge Graph
          </span>
          <span className="mt-1 text-[0.6rem] uppercase tracking-[0.16em] font-semibold text-muted">
            Signal mapping for channel narratives
          </span>
        </div>
        <nav aria-label="Visualization views" className="flex gap-5 text-[0.76rem]">
          {ROUTES.map((route) => {
            if (route.disabled) {
              return (
                <span
                  key={route.label}
                  aria-disabled="true"
                  className="text-ink/35 cursor-not-allowed select-none"
                >
                  {route.label}
                </span>
              );
            }
            if (route.detailOnly) {
              if (!onDetail) {
                return (
                  <span
                    key={route.label}
                    aria-disabled="true"
                    className="text-ink/35 cursor-not-allowed select-none"
                  >
                    {route.label}
                  </span>
                );
              }
              return (
                <NavItem
                  key={route.label}
                  to={location.pathname}
                  active={true}
                >
                  {route.label}
                </NavItem>
              );
            }
            return (
              <NavItem key={route.label} to={route.path!} end active={onRoot && route.path === "/"}>
                {route.label}
              </NavItem>
            );
          })}
        </nav>
        <div className="font-mono text-[0.68rem] text-muted whitespace-nowrap">● LIVE</div>
      </div>
    </header>
  );
}
