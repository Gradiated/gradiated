import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  LoaderCircle,
  WalletCards,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  balanceTransactionsQuery,
  billingAccountQuery,
  type BalanceTransaction,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { TopUpBalance } from "@/components/top-up-balance";
import { useProductContext } from "@/hooks/use-product-context";
import { formatNanoUsd } from "@/lib/format";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

const transactionTime = new Intl.DateTimeFormat(undefined, {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const TRANSACTION_LABEL: Record<BalanceTransaction["type"], string> = {
  adjustment: "Adjustment",
  chargeback: "Chargeback",
  credit: "Credit",
  payment: "Payment",
  refund: "Refund",
  topup: "Top-up",
  usage: "Inference usage",
};

export const BillingPage = () => {
  const context = useProductContext();
  const [checkoutReturn, setCheckoutReturn] = useState<
    "success" | "cancelled" | null
  >(() => {
    const value = new URLSearchParams(window.location.search).get("topup");

    return value === "success" || value === "cancelled" ? value : null;
  });
  const refetchInterval = checkoutReturn === "success" ? 2_000 : false;
  const account = useQuery({
    ...billingAccountQuery(context.organizationId),
    refetchInterval,
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
    <ConsolePage
      page="billing"
      title="Billing"
      description={`Balance and transaction history for ${context.selectedOrganization?.name ?? "the selected organization"}.`}
    >
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
          ) : account.isError ? (
            <LoadFailed
              subject="the balance"
              retrying={account.isFetching}
              onRetry={() => void account.refetch()}
              className="min-h-0 px-0"
            />
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

      <BalanceHistory
        key={context.organizationId}
        organizationId={context.organizationId}
        refetchInterval={refetchInterval}
      />
    </ConsolePage>
  );
};

const BalanceHistory = ({
  organizationId,
  refetchInterval,
}: {
  organizationId: string;
  refetchInterval: number | false;
}) => {
  const [cursors, setCursors] = useState<string[]>([]);
  const transactions = useQuery({
    ...balanceTransactionsQuery(organizationId, cursors.at(-1)),
    refetchInterval,
  });

  return (
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
      ) : transactions.isError ? (
        <LoadFailed
          subject="balance history"
          retrying={transactions.isFetching}
          onRetry={() => void transactions.refetch()}
        />
      ) : transactions.data?.data.length ? (
        <Table aria-label="Balance history" className="text-base">
          <TableBody>
            {transactions.data.data.map((transaction) => {
              const positive = BigInt(transaction.amount) > 0n;

              return (
                <TableRow key={transaction.id} className="hover:bg-transparent">
                  <TableCell className="whitespace-normal py-4 pl-5 pr-0">
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
                          {TRANSACTION_LABEL[transaction.type]}
                        </p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {transactionTime.format(
                            new Date(transaction.created_at),
                          )}
                        </p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-normal py-4 pl-5 pr-5 text-right">
                    <p
                      className={
                        positive ? "font-medium text-[#536718]" : "font-medium"
                      }
                    >
                      {positive ? "+" : ""}
                      {formatNanoUsd(transaction.amount)}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {formatNanoUsd(transaction.balance_after)} balance
                    </p>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      ) : (
        <div className="grid min-h-48 place-items-center px-6 text-center text-sm text-muted-foreground">
          No balance transactions yet.
        </div>
      )}
      {cursors.length > 0 || transactions.data?.next_cursor ? (
        <div className="flex justify-end gap-2 border-t px-5 py-3">
          <Button
            variant="outline"
            size="sm"
            disabled={cursors.length === 0 || transactions.isFetching}
            onClick={() => setCursors((previous) => previous.slice(0, -1))}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={
              !transactions.data?.next_cursor ||
              transactions.isFetching ||
              transactions.isError
            }
            onClick={() => {
              const cursor = transactions.data?.next_cursor;

              if (cursor) setCursors((previous) => [...previous, cursor]);
            }}
          >
            Next
          </Button>
        </div>
      ) : null}
    </section>
  );
};
