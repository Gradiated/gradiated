import { Link, Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { ConsolePage } from "@/pages/console-page";

const NAV_GROUPS = [
  {
    heading: "Workspace",
    links: [{ to: "/settings/workspace", label: "General" }],
  },
  {
    heading: "Organization",
    links: [
      { to: "/settings/organization", label: "General" },
      { to: "/settings/members", label: "Members" },
    ],
  },
] as const;

export const SettingsLayout = () => (
  <ConsolePage page="settings" title="Settings">
    <div className="flex flex-col gap-7 md:flex-row md:gap-10">
      <SettingsNav />
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  </ConsolePage>
);

const SettingsNav = () => (
  <nav
    aria-label="Settings"
    className="-mx-5 flex shrink-0 gap-4 overflow-x-auto px-5 pb-1 md:mx-0 md:w-48 md:flex-col md:gap-5 md:overflow-visible md:px-0 md:pb-0"
  >
    {NAV_GROUPS.map((group) => (
      <div
        key={group.heading}
        role="group"
        aria-label={group.heading}
        className="shrink-0 border-l pl-4 first:border-l-0 first:pl-0 md:border-l-0 md:pl-0"
      >
        <p className="mb-1.5 px-0.5 text-xs font-medium text-muted-foreground md:px-2.5">
          {group.heading}
        </p>
        <div className="flex gap-1.5 md:flex-col md:gap-0.5">
          {group.links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="rounded-full border bg-card px-3 py-1.5 text-sm whitespace-nowrap transition-colors hover:bg-accent data-[status=active]:border-primary data-[status=active]:bg-primary data-[status=active]:text-primary-foreground md:rounded-md md:border-0 md:bg-transparent md:px-2.5 md:data-[status=active]:bg-sidebar-accent md:data-[status=active]:font-medium md:data-[status=active]:text-foreground"
            >
              {link.label}
            </Link>
          ))}
        </div>
      </div>
    ))}
  </nav>
);

export const SettingsHeader = ({
  title,
  description,
  actions,
}: {
  title: string;
  description: ReactNode;
  actions?: ReactNode;
}) => (
  <div className="mb-5 flex items-start justify-between gap-4">
    <div className="min-w-0">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">
        {description}
      </p>
    </div>
    {actions ? <div className="shrink-0">{actions}</div> : null}
  </div>
);
