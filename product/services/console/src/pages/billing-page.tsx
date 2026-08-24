import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  LoaderCircle,
  WalletCards,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  getBillingAccount,
  listBalanceTransactions,
  type BalanceTransaction,
} from "@/api/queries";
import { AppShell } from "@/components/app-shell";
import { TopUpBalance } from "@/components/top-up-balance";
import { useProductContext } from "@/hooks/use-product-context";
import { formatNanoUsd } from "@/lib/format";

const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));

const transactionLabel = (transaction: BalanceTransaction) => {
  const labels: Record<BalanceTransaction["type"], string> = {
    adjustment: "Adjustment",
    chargeback: "Chargeback",
    credit: "Credit",
    payment: "Payment",
    refund: "Refund",
    topup: "Top-up",
    usage: "Inference usage",
  };
  return labels[transaction.type];
};

export const BillingPage = () => {
  const context = useProductContext();
  const [checkoutReturn, setCheckoutReturn] = useState<
    "success" | "cancelled" | null
  >(() => {
    const value = new URLSearchParams(window.location.search).get("topup");
    return value === "success" || value === "cancelled" ? value : null;
  });
  const account = useQuery({
    queryKey: ["billing", context.organizationId],
    queryFn: () => getBillingAccount(context.organizationId),
    enabled: Boolean(context.organizationId),
    refetchInterval: checkoutReturn === "success" ? 2_000 : false,
  });
  const transactions = useQuery({
    queryKey: ["balance-transactions", context.organizationId],
    queryFn: () => listBalanceTransactions(context.organizationId),
    enabled: Boolean(context.organizationId),
    refetchInterval: checkoutReturn === "success" ? 2_000 : false,
  });

  useEffect(() => {
    if (!checkoutReturn) return;
    const timeout = window.setTimeout(() => {
      setCheckoutReturn(null);
      window.history.replaceState({}, "", "/billing");
    }, 15_000);
    return () => window.clearTimeout(timeout);
  }, [checkoutReturn]);

  return (
    <AppShell
      user={context.user}
      organizationId={context.organizationId}
      workspaces={context.workspaces}
      workspaceId={context.workspaceId}
      onSelectOrganization={context.selectOrganization}
      onSelectWorkspace={context.selectWorkspace}
      onSignOut={context.signOut}
      activePage="billing"
      pageTitle="Billing"
    >
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-5xl">
          <div className="mb-8">
            <h1 className="text-3xl font-semibold tracking-[-0.035em]">
              Billing
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Balance and transaction history for{" "}
              {context.selectedOrganization?.name ??
                "the selected organization"}
              .
            </p>
          </div>

          {checkoutReturn ? (
            <div
              className={`mb-6 rounded-lg border px-4 py-3 text-sm ${
                checkoutReturn === "success"
                  ? "border-[#c8da86] bg-[#f7fbe9] text-[#445313]"
                  : "bg-muted/50 text-muted-foreground"
              }`}
            >
              {checkoutReturn === "success"
                ? "Payment completed. Your balance and history will update as soon as Stripe confirms it."
                : "Checkout was cancelled. Your balance was not changed."}
            </div>
          ) : null}

          <div className="mb-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
            <section className="overflow-hidden rounded-xl bg-[#181914] p-6 text-white shadow-sm">
              {account.isLoading ? (
                <LoaderCircle className="size-5 animate-spin text-white/50" />
              ) : (
                <div>
                  <div className="mb-5 flex items-center gap-2 text-sm text-white/55">
                    <WalletCards className="size-4" />
                    Available balance
                  </div>
                  <p className="text-4xl font-semibold tracking-[-0.04em]">
                    {account.data ? formatNanoUsd(account.data.balance) : "—"}
                  </p>
                </div>
              )}
            </section>
            {account.data?.mode === "prepaid" && context.organizationId ? (
              <TopUpBalance organizationId={context.organizationId} />
            ) : null}
          </div>

          <section className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="border-b px-5 py-4">
              <h2 className="font-medium">Balance history</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Payments, credits, refunds and usage.
              </p>
            </div>
            {transactions.isLoading ? (
              <div className="grid min-h-48 place-items-center">
                <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
              </div>
            ) : transactions.data?.data.length ? (
              <div className="divide-y">
                {transactions.data.data.map((transaction) => {
                  const positive = BigInt(transaction.amount) > 0n;
                  return (
                    <div
                      key={transaction.id}
                      className="flex items-center justify-between gap-5 px-5 py-4"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
                          {positive ? (
                            <ArrowDownLeft className="size-4" />
                          ) : (
                            <ArrowUpRight className="size-4" />
                          )}
                        </span>
                        <div className="min-w-0">
                          <p className="font-medium">
                            {transactionLabel(transaction)}
                          </p>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {formatDateTime(transaction.created_at)}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p
                          className={
                            positive
                              ? "font-medium text-[#536718]"
                              : "font-medium"
                          }
                        >
                          {positive ? "+" : ""}
                          {formatNanoUsd(transaction.amount)}
                        </p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {formatNanoUsd(transaction.balance_after)} balance
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="grid min-h-48 place-items-center px-6 text-center text-sm text-muted-foreground">
                No balance transactions yet.
              </div>
            )}
          </section>
        </div>
      </main>
    </AppShell>
  );
};
