import { Link, type LinkProps } from "@tanstack/react-router";
import { ArrowLeft, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

export const SectionCard = ({
  title,
  description,
  actions,
  children,
  className,
  contentClassName,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}) => (
  <Card className={cn("overflow-hidden shadow-sm", className)}>
    <CardHeader className="flex-row items-start justify-between gap-4 border-b p-5">
      <div className="min-w-0">
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? (
          <CardDescription className="mt-1">{description}</CardDescription>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 gap-2">{actions}</div> : null}
    </CardHeader>
    <CardContent className={cn("p-5", contentClassName)}>
      {children}
    </CardContent>
  </Card>
);

export const Stat = ({
  label,
  value,
  detail,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}) => (
  <div className="min-w-0 p-5" role="group" aria-label={label}>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className="mt-2 truncate text-2xl font-semibold tracking-[-0.035em] tabular-nums">
      {value}
    </p>
    {detail ? (
      <p className="mt-1 truncate text-xs text-muted-foreground">{detail}</p>
    ) : null}
  </div>
);

export const StatGrid = ({ children }: { children: ReactNode }) => (
  <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border bg-border shadow-sm lg:grid-cols-4 [&>*]:bg-card">
    {children}
  </div>
);

export const EmptyState = ({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: ReactNode;
  action?: ReactNode;
}) => (
  <div className="grid min-h-64 place-items-center rounded-xl border border-dashed bg-card px-6 py-10 text-center">
    <div className="max-w-sm">
      <span className="mx-auto grid size-10 place-items-center rounded-full bg-muted text-muted-foreground [&_svg]:size-5">
        {icon}
      </span>
      <p className="mt-4 text-sm font-medium">{title}</p>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  </div>
);

export const SkeletonRows = ({
  columns,
  rows = 5,
}: {
  columns: number;
  rows?: number;
}) =>
  Array.from({ length: rows }, (_, row) => (
    <TableRow key={row} aria-hidden="true">
      {Array.from({ length: columns }, (_, column) => (
        <TableCell key={column} className="h-14 first:pl-5 last:pr-5">
          <Skeleton className={column === 0 ? "h-4 w-36" : "h-4 w-20"} />
        </TableCell>
      ))}
    </TableRow>
  ));

export const LoadMore = ({
  hasMore,
  loading,
  onLoad,
}: {
  hasMore: boolean;
  loading: boolean;
  onLoad: () => void;
}) =>
  hasMore ? (
    <div className="flex justify-center border-t p-3">
      <Button variant="ghost" size="sm" disabled={loading} onClick={onLoad}>
        {loading ? <LoaderCircle className="animate-spin" /> : null}
        Load more
      </Button>
    </div>
  ) : null;

export const BackLink = ({
  to,
  params,
  children,
}: {
  to: NonNullable<LinkProps["to"]>;
  params?: LinkProps["params"];
  children: ReactNode;
}) => (
  <Link
    to={to}
    {...(params ? { params } : {})}
    className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
  >
    <ArrowLeft className="size-3.5" />
    {children}
  </Link>
);

export const DetailList = ({
  items,
  className,
}: {
  items: readonly { label: string; value: ReactNode }[];
  className?: string;
}) => (
  <dl className={cn("grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2", className)}>
    {items.map((item) => (
      <div
        key={item.label}
        className="flex min-w-0 justify-between gap-4 border-b border-dashed pb-2"
      >
        <dt className="text-muted-foreground">{item.label}</dt>
        <dd className="min-w-0 truncate text-right font-medium tabular-nums">
          {item.value}
        </dd>
      </div>
    ))}
  </dl>
);

export const TableCard = ({
  label,
  busy = false,
  children,
  footer,
}: {
  label: string;
  busy?: boolean;
  children: ReactNode;
  footer?: ReactNode;
}) => (
  <section
    aria-label={label}
    aria-busy={busy}
    className="overflow-hidden rounded-lg border bg-card"
  >
    <div className="overflow-x-auto">{children}</div>
    {footer}
  </section>
);
