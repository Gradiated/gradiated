import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ArrowDownLeft, ArrowUpRight, WalletCards } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { z } from "zod";

import {
  balanceTransactionsQuery,
  billingAccountQuery,
  useSaveCard,
  type BalanceTransaction,
} from "@/api/queries";
import { Skeleton } from "@/components/ui/skeleton";
import { useInfiniteScroll } from "@/hooks/use-infinite-scroll";
import { canManageOrganization } from "@/lib/roles";
import { Table, TableBody, TableCell, TableRow } from "@/components/ui/table";
import { AutoTopUpDialog } from "@/components/billing/auto-top-up-dialog";
import { CardDialog } from "@/components/billing/card-dialog";
import {
  PaymentSettings,
  PaymentSettingsSkeleton,
} from "@/components/billing/payment-settings";
import { TopUpDialog } from "@/components/billing/top-up-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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

// Shown once on returning from Checkout; success polls until the webhook lands.
const CHECKOUT_RETURN = {
  success: {
    kind: "success",
    title: "Payment completed",
    description: "Your balance updates as soon as Stripe confirms it.",
  },
  cancelled: {
    kind: "info",
    title: "Checkout cancelled",
    description: "Your balance was not changed.",
  },
} as const;

type CheckoutReturn = keyof typeof CHECKOUT_RETURN;

const checkoutReturnFromUrl = (): CheckoutReturn | null => {
  const value = new URLSearchParams(window.location.search).get("topup");

  return value && value in CHECKOUT_RETURN ? (value as CheckoutReturn) : null;
};

// Work started by a Stripe redirect is kept for this tab until it finishes,
// so a reload or a visit to another page does not lose it.
const PENDING_CHECKOUT = "billing:pending-checkout";
const PENDING_CARD_SETUP = "billing:pending-card-setup";
const CHECKOUT_POLL_MS = 120_000;
const CARD_SETUP_RETRY_MS = 10 * 60_000;

// A card setup belongs to one organization; a Checkout Session id is unique.
const PendingSchema = z.object({
  id: z.string().min(1),
  organizationId: z.string().optional(),
  until: z.number(),
});

type Pending = z.infer<typeof PendingSchema>;

const readPending = (key: string, organizationId?: string): Pending | null => {
  try {
    const pending = PendingSchema.nullable().parse(
      JSON.parse(window.sessionStorage.getItem(key) ?? "null"),
    );
    if (
      pending &&
      pending.organizationId === organizationId &&
      pending.until > Date.now()
    )
      return pending;
  } catch {
    // An unreadable entry is dropped below.
  }
  window.sessionStorage.removeItem(key);

  return null;
};

const writePending = (key: string, pending: Pending) =>
  window.sessionStorage.setItem(key, JSON.stringify(pending));

// The Checkout Session a successful return credits: from its success URL on
// return, or from storage until its credit lands.
const pendingCheckout = (): Pending | null => {
  const search = new URLSearchParams(window.location.search);
  const id = search.get("session_id");
  if (search.get("topup") === "success" && id) {
    const pending = { id, until: Date.now() + CHECKOUT_POLL_MS };
    writePending(PENDING_CHECKOUT, pending);

    return pending;
  }

  return readPending(PENDING_CHECKOUT);
};

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
  const [checkoutReturn, setCheckoutReturn] = useState(checkoutReturnFromUrl);
  const [checkout, setCheckout] = useState(pendingCheckout);
  const checkoutSession = checkout?.id ?? null;
  const canManage = canManageOrganization(context.selectedOrganization);
  // Polls while a saved-card charge is settling or a Checkout webhook is due.
  const account = useQuery({
    ...billingAccountQuery(context.organizationId),
    refetchInterval: (query) =>
      query.state.data?.top_up_pending ||
      checkoutReturn === "success" ||
      checkoutSession
        ? 2_000
        : false,
  });
  const prepaid = account.data?.mode === "prepaid" ? account.data : null;
  const [dialog, setDialog] = useState<"top-up" | "auto-top-up" | null>(null);
  // The card dialog can open over the top-up dialog, so it has its own state.
  const [cardOpen, setCardOpen] = useState(false);
  const closeDialog = (open: boolean) => {
    if (!open) setDialog(null);
  };

  // History refreshes once whenever the balance moves, instead of polling.
  const queryClient = useQueryClient();
  const balance = account.data?.balance;
  useEffect(() => {
    if (balance === undefined) return;

    void queryClient.invalidateQueries({
      queryKey: balanceTransactionsQuery(context.organizationId).queryKey,
    });
  }, [balance, context.organizationId, queryClient]);

  // The return's polling ends once the history shows this session's credit,
  // so other balance movements do not end it early.
  const history = useInfiniteQuery({
    ...balanceTransactionsQuery(context.organizationId),
    enabled: checkoutSession !== null,
  });
  const checkoutCredited = Boolean(
    checkoutSession &&
    history.data?.pages.some((page) =>
      page.data.some(
        (row) =>
          row.source_type === "stripe_checkout_session" &&
          row.stripe_id === checkoutSession,
      ),
    ),
  );
  useEffect(() => {
    if (!checkout) return;

    const finish = () => {
      window.sessionStorage.removeItem(PENDING_CHECKOUT);
      setCheckout(null);
      setCheckoutReturn(null);
    };
    if (checkoutCredited) return finish();

    // The webhook can take a while; stop after the polling window regardless.
    const timeout = window.setTimeout(finish, checkout.until - Date.now());

    return () => window.clearTimeout(timeout);
  }, [checkout, checkoutCredited]);

  // A card that needed a redirect to confirm comes back with its SetupIntent,
  // which is kept until the card is saved so a failed save can be retried.
  const { mutate: saveRedirectedCard } = useSaveCard(context.organizationId);
  useEffect(() => {
    if (!context.organizationId) return;

    const search = new URLSearchParams(window.location.search);
    const setupIntentId = search.get("setup_intent");
    if (setupIntentId) {
      window.history.replaceState({}, "", "/billing");
      if (search.get("redirect_status") !== "succeeded") {
        toast.error("The card was not confirmed.", { id: "card-confirmed" });
        return;
      }

      writePending(PENDING_CARD_SETUP, {
        id: setupIntentId,
        organizationId: context.organizationId,
        until: Date.now() + CARD_SETUP_RETRY_MS,
      });
    }

    const pending = readPending(PENDING_CARD_SETUP, context.organizationId);
    if (!pending) return;

    saveRedirectedCard(pending.id, {
      onSuccess: () => window.sessionStorage.removeItem(PENDING_CARD_SETUP),
    });
  }, [context.organizationId, saveRedirectedCard]);

  useEffect(() => {
    if (!checkoutReturn) return;

    const { kind, title, description } = CHECKOUT_RETURN[checkoutReturn];
    // A fixed id keeps a remount from showing the same toast twice.
    toast[kind](title, { id: `topup-${checkoutReturn}`, description });
    window.history.replaceState({}, "", "/billing");

    // A return without a session id polls for the window and then stops.
    const timeout = window.setTimeout(
      () => setCheckoutReturn(null),
      CHECKOUT_POLL_MS,
    );

    return () => window.clearTimeout(timeout);
  }, [checkoutReturn]);

  return (
    <ConsolePage
      page="billing"
      title="Billing"
      description={`Balance and transaction history for ${context.selectedOrganization?.name ?? "the selected organization"}.`}
    >
      <Card className="mb-8 shadow-sm">
        <div className="flex items-center justify-between gap-6 p-6">
          {account.isLoading ? (
            <div aria-busy="true" aria-label="Loading balance">
              <Skeleton className="h-3.5 w-28" />
              <Skeleton className="mt-3 h-10 w-44" />
            </div>
          ) : account.isError ? (
            <LoadFailed
              subject="the balance"
              retrying={account.isFetching}
              onRetry={() => void account.refetch()}
              className="min-h-0 px-0"
            />
          ) : (
            <div>
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <WalletCards className="size-4" />
                Available balance
              </p>
              <p className="mt-2 text-4xl font-semibold tracking-[-0.04em]">
                {account.data ? formatNanoUsd(account.data.balance) : "—"}
              </p>
            </div>
          )}
          {account.isLoading ? (
            <Skeleton className="h-9 w-20 rounded-md" />
          ) : prepaid ? (
            <Button disabled={!canManage} onClick={() => setDialog("top-up")}>
              Top up
            </Button>
          ) : null}
        </div>
      </Card>

      {account.isLoading ? <PaymentSettingsSkeleton /> : null}
      {prepaid ? (
        <PaymentSettings
          account={prepaid}
          canManage={canManage}
          onEditAutoTopUp={() => setDialog("auto-top-up")}
          onChangeCard={() => setCardOpen(true)}
        />
      ) : null}

      {prepaid && dialog === "top-up" ? (
        <TopUpDialog
          account={prepaid}
          open
          onOpenChange={closeDialog}
          onChangeCard={() => setCardOpen(true)}
        />
      ) : null}
      {prepaid ? (
        <CardDialog
          account={prepaid}
          open={cardOpen}
          onOpenChange={setCardOpen}
        />
      ) : null}
      {prepaid && dialog === "auto-top-up" ? (
        <AutoTopUpDialog account={prepaid} open onOpenChange={closeDialog} />
      ) : null}

      <BalanceHistory
        key={context.organizationId}
        organizationId={context.organizationId}
      />
    </ConsolePage>
  );
};

const BalanceHistory = ({ organizationId }: { organizationId: string }) => {
  const transactions = useInfiniteQuery(
    balanceTransactionsQuery(organizationId),
  );
  const loadMoreRef = useInfiniteScroll(transactions);
  const rows = [
    ...new Map(
      transactions.data?.pages
        .flatMap((page) => page.data)
        .map((row) => [row.id, row]),
    ).values(),
  ];

  return (
    <section>
      <h2 className="text-lg font-semibold tracking-tight">Balance history</h2>
      <p className="mb-4 mt-1 text-sm text-muted-foreground">
        Payments, credits, refunds and usage.
      </p>
      <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
        {transactions.isLoading ? (
          <Table aria-label="Loading balance history" aria-busy="true">
            <TableBody>
              <TransactionSkeletonRows count={5} />
            </TableBody>
          </Table>
        ) : rows.length || transactions.isFetchingNextPage ? (
          <Table aria-label="Balance history" className="text-base">
            <TableBody>
              {rows.map((transaction) => {
                const positive = BigInt(transaction.amount) > 0n;

                return (
                  <TableRow
                    key={transaction.id}
                    className="hover:bg-transparent"
                  >
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
                    </TableCell>
                  </TableRow>
                );
              })}
              {transactions.isFetchingNextPage ? (
                <TransactionSkeletonRows count={3} />
              ) : null}
            </TableBody>
          </Table>
        ) : transactions.isError ? null : (
          <div className="grid min-h-48 place-items-center px-6 text-center text-sm text-muted-foreground">
            No balance transactions yet.
          </div>
        )}
        {transactions.isError ? (
          <LoadFailed
            subject="balance history"
            retrying={transactions.isFetching}
            onRetry={() =>
              void (transactions.isFetchNextPageError
                ? transactions.fetchNextPage()
                : transactions.refetch())
            }
          />
        ) : null}
        {transactions.hasNextPage ? (
          <div
            ref={loadMoreRef}
            className="h-4"
            role={transactions.isFetchingNextPage ? "status" : undefined}
            aria-label={
              transactions.isFetchingNextPage
                ? "Loading older transactions"
                : undefined
            }
          >
            {transactions.isFetchingNextPage ? (
              <span className="sr-only">Loading older transactions</span>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
};

const TransactionSkeletonRows = ({ count }: { count: number }) =>
  Array.from({ length: count }, (_, index) => (
    <TableRow
      key={`loading-${index}`}
      aria-hidden="true"
      className="hover:bg-transparent"
    >
      <TableCell className="py-4 pl-5">
        <div className="flex items-center gap-3">
          <Skeleton className="size-9 rounded-lg" />
          <div className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-36" />
          </div>
        </div>
      </TableCell>
      <TableCell className="py-4 pr-5">
        <Skeleton className="ml-auto h-4 w-20" />
        <Skeleton className="ml-auto mt-2 h-3 w-28" />
      </TableCell>
    </TableRow>
  ));
