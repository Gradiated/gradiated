import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import {
  balanceTransactionsQuery,
  billingAccountQuery,
  createTopUp,
  type BillingAccount,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { analytics } from "@/lib/analytics";
import { errorMessage, httpStatus } from "@/lib/errors";
import { formatNanoUsd } from "@/lib/format";
import { parseUsdAmount } from "@/lib/money";
import { cn } from "@/lib/utils";
import { SavedCardSummary } from "./card-brand-mark";
import { UsdInput } from "./usd-input";

const PRESETS = ["25", "50", "100", "250"];

export const TopUpDialog = ({
  account,
  open,
  onOpenChange,
  onChangeCard,
}: {
  account: BillingAccount;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChangeCard: () => void;
}) => {
  const queryClient = useQueryClient();
  const [value, setValue] = useState("50");
  const [touched, setTouched] = useState(false);
  const amount = parseUsdAmount(value);
  const card = account.payment_method;
  // One key per attempt: a retry after a lost response returns the first
  // result instead of charging again. A new amount starts a new attempt.
  const attempt = useRef<{ key: string; amount: bigint } | null>(null);

  const pay = useMutation({
    mutationFn: (method: "card" | "checkout") => {
      analytics.track("billing_top_up_clicked", {
        organization_id: account.organization_id,
      });

      if (attempt.current?.amount !== amount) {
        attempt.current = { key: crypto.randomUUID(), amount: amount! };
      }

      return createTopUp(account.organization_id, {
        amount: amount!.toString(),
        method,
        idempotency_key: attempt.current.key,
      });
    },
    onSettled: (_data, error) => {
      // Only a request that never got an answer is retried with the same key.
      if (!error || httpStatus(error) !== undefined) attempt.current = null;
    },
    onSuccess: async (topUp) => {
      if (topUp.checkout_url) {
        window.location.assign(topUp.checkout_url);
        return;
      }

      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: billingAccountQuery(account.organization_id).queryKey,
        }),
        queryClient.invalidateQueries({
          queryKey: balanceTransactionsQuery(account.organization_id).queryKey,
        }),
      ]);
      toast.success(
        topUp.status === "paid"
          ? `Added ${formatNanoUsd(amount!)} to your balance.`
          : "Payment is processing. Your balance updates when it completes.",
      );
      onOpenChange(false);
    },
    // A decline offers Checkout with another card; the dialog stays open.
    onError: (error) => {
      const message = errorMessage(error, "The payment could not be started.");

      if (httpStatus(error) === 402) {
        toast.error("Payment declined", {
          description: message,
          action: {
            label: "Pay with another card",
            onClick: () => submit("checkout"),
          },
        });
      } else {
        toast.error(message);
      }
    },
  });

  const submit = (method: "card" | "checkout") => {
    setTouched(true);
    if (amount !== null) pay.mutate(method);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-md"
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Top up</DialogTitle>
          <DialogDescription>
            Funds are added to your balance as soon as the payment succeeds.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-4 gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              aria-pressed={value === preset}
              onClick={() => setValue(preset)}
              className={cn(
                "rounded-lg border py-3 text-sm font-medium transition-colors",
                value === preset
                  ? "border-foreground bg-foreground text-background"
                  : "hover:bg-muted",
              )}
            >
              ${preset}
            </button>
          ))}
        </div>

        <Field data-invalid={touched && amount === null}>
          <FieldLabel htmlFor="top-up-amount">Amount</FieldLabel>
          <UsdInput
            id="top-up-amount"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
          {touched && amount === null ? (
            <FieldError>Enter an amount between $5 and $10,000.</FieldError>
          ) : null}
        </Field>

        <SavedCardSummary card={card}>
          <button
            type="button"
            className="ml-auto shrink-0 font-medium underline underline-offset-4 hover:text-foreground/80"
            onClick={onChangeCard}
          >
            {card ? "Change" : "Add card"}
          </button>
        </SavedCardSummary>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={pay.isPending}
            onClick={() => submit(card ? "card" : "checkout")}
          >
            {pay.isPending ? <LoaderCircle className="animate-spin" /> : null}
            {card
              ? `Pay ${amount === null ? "" : formatNanoUsd(amount)}`.trim()
              : "Continue to Stripe"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
