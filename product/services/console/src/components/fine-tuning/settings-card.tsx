import type { ReactNode } from "react";

export const SettingsCard = ({ children }: { children: ReactNode }) => (
  <div className="max-w-2xl divide-y rounded-lg border bg-card">{children}</div>
);

export const SettingRow = ({
  title,
  description,
  children,
}: {
  title: string;
  description: ReactNode;
  children: ReactNode;
}) => (
  <div className="flex items-start justify-between gap-6 p-5">
    <div>
      <p className="text-sm font-medium">{title}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">
        {description}
      </p>
    </div>
    {children}
  </div>
);
