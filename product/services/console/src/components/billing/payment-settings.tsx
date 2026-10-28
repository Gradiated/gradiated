import { useMutation } from "@tanstack/react-query";
import { ExternalLink, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import { createPaymentMethodSession, type BillingAccount } from "@/api/queries";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/errors";
import { formatNanoUsd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CardBrandMark, cardLabel } from "./card-brand-mark";

const SettingRow = ({
  title,
  description,
  leading,
  action,
}: {
  title: ReactNode;
  description: ReactNode;
  leading?: ReactNode;
  action: ReactNode;
}) => (
  <Card className="shadow-sm">
    <div className="flex flex-col gap-4 p-6 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-center gap-4">
        {leading}
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-medium">{title}</div>
          <div className="mt-1 text-sm text-muted-foreground">
            {description}
          </div>
        </div>
      </div>
      <div className="shrink-0">{action}</div>
    </div>
  </Card>
);

// Placeholder rows shaped like the auto top-up, card and invoices rows.
export const PaymentSettingsSkeleton = () => (
  <section className="mb-8" aria-busy="true" aria-label="Loading payments">
    <h2 className="text-lg font-semibold tracking-tight">Payments</h2>
    <Skeleton className="mb-4 mt-2 h-4 w-64" />
    <div className="space-y-4">
      {[false, true, false].map((leading, index) => (
        <Card key={index} className="shadow-sm">
          <div className="flex items-center justify-between gap-4 p-6">
            <div className="flex items-center gap-4">
              {leading ? <Skeleton className="h-6 w-9 rounded-[5px]" /> : null}
              <div className="space-y-2">
                <Skeleton className="h-4 w-36" />
                <Skeleton className="h-3.5 w-64" />
              </div>
            </div>
            <Skeleton className="h-8 w-20 rounded-md" />
          </div>
        </Card>
      ))}
    </div>
  </section>
);

const StatusBadge = ({ on }: { on: boolean }) => (
  <Badge variant="outline" className="gap-1.5 font-normal">
    <span
      className={cn(
        "size-1.5 rounded-full",
        on ? "bg-[#7a9a1f]" : "bg-muted-foreground/40",
      )}
    />
    {on ? "On" : "Off"}
  </Badge>
);

const expiry = (month: number | null, year: number | null) =>
  month && year
    ? `Expires ${String(month).padStart(2, "0")}/${String(year).slice(-2)}`
    : null;

const AutoTopUpDescription = ({
  settings,
}: {
  settings: BillingAccount["auto_top_up"];
}) => {
  if (settings.failure) {
    return (
      <span className="text-destructive">
        Turned off after a failed payment: {settings.failure}
      </span>
    );
  }

  if (settings.enabled && settings.amount && settings.threshold) {
    return (
      <>
        Adds{" "}
        <span className="font-medium text-foreground">
          {formatNanoUsd(settings.amount)}
        </span>{" "}
        when your balance falls below{" "}
        <span className="font-medium text-foreground">
          {formatNanoUsd(settings.threshold)}
        </span>
        .
      </>
    );
  }

  return "Charge your card automatically so your balance never runs out.";
};

export const PaymentSettings = ({
  account,
  canManage,
  onEditAutoTopUp,
  onChangeCard,
}: {
  account: BillingAccount;
  canManage: boolean;
  onEditAutoTopUp: () => void;
  onChangeCard: () => void;
}) => {
  const card = account.payment_method;
  const settings = account.auto_top_up;
  const portal = useMutation({
    mutationFn: () => createPaymentMethodSession(account.organization_id),
    onSuccess: (session) => window.location.assign(session.url),
    meta: { errorMessage: "Stripe could not be opened." },
  });

  return (
    <section className="mb-8">
      <h2 className="text-lg font-semibold tracking-tight">Payments</h2>
      <p className="mb-4 mt-1 text-sm text-muted-foreground">
        {canManage
          ? "How your organization pays for inference."
          : "Only admins can change payment settings."}
      </p>
      <div className="space-y-4">
        <SettingRow
          title={
            <>
              Auto top-up
              <StatusBadge on={settings.enabled} />
            </>
          }
          description={<AutoTopUpDescription settings={settings} />}
          action={
            <Button
              variant="outline"
              size="sm"
              disabled={!canManage || !card}
              onClick={onEditAutoTopUp}
            >
              {settings.enabled
                ? "Edit"
                : settings.threshold
                  ? "Turn on"
                  : "Set up"}
            </Button>
          }
        />
        <SettingRow
          leading={<CardBrandMark brand={card?.brand ?? null} />}
          title={card ? cardLabel(card, "long") : "No card saved"}
          description={
            card
              ? [
                  expiry(card.exp_month, card.exp_year),
                  "Used for top-ups and auto top-up",
                ]
                  .filter(Boolean)
                  .join(" · ")
              : "Add a card to top up in one step and turn on auto top-up."
          }
          action={
            <Button
              variant="outline"
              size="sm"
              disabled={!canManage}
              onClick={onChangeCard}
            >
              {card ? "Change" : "Add card"}
            </Button>
          }
        />
        <SettingRow
          title="Invoices and billing details"
          description="Download invoices and update billing details in Stripe."
          action={
            <Button
              variant="outline"
              size="sm"
              disabled={
                !canManage || !account.billing_portal || portal.isPending
              }
              onClick={() => portal.mutate()}
            >
              Manage billing
              {portal.isPending ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <ExternalLink />
              )}
            </Button>
          }
        />
      </div>
    </section>
  );
};
