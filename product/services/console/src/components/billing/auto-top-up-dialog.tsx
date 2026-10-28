import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import {
  billingAccountQuery,
  updateAutoTopUp,
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
import { Switch } from "@/components/ui/switch";
import { formatNanoUsdInput, parseUsdAmount } from "@/lib/money";
import { SavedCardSummary } from "./card-brand-mark";
import { cn } from "@/lib/utils";

import { UsdInput } from "./usd-input";

const DEFAULT_THRESHOLD = "10000000000";
const DEFAULT_AMOUNT = "50000000000";

export const AutoTopUpDialog = ({
  account,
  open,
  onOpenChange,
}: {
  account: BillingAccount;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => {
  const queryClient = useQueryClient();
  const settings = account.auto_top_up;
  // Opening the dialog to set up, or after a failed charge, means turning it on.
  const [enabled, setEnabled] = useState(
    settings.enabled ||
      settings.threshold === null ||
      Boolean(settings.failure),
  );
  const [threshold, setThreshold] = useState(
    formatNanoUsdInput(settings.threshold ?? DEFAULT_THRESHOLD),
  );
  const [amount, setAmount] = useState(
    formatNanoUsdInput(settings.amount ?? DEFAULT_AMOUNT),
  );
  const [touched, setTouched] = useState(false);
  const thresholdValue = parseUsdAmount(threshold, 0n);
  const amountValue = parseUsdAmount(amount);

  const save = useMutation({
    // Turning it off keeps the saved threshold and amount for next time.
    mutationFn: () =>
      updateAutoTopUp(
        account.organization_id,
        enabled
          ? {
              enabled,
              threshold: thresholdValue!.toString(),
              amount: amountValue!.toString(),
            }
          : { enabled },
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(
        billingAccountQuery(account.organization_id).queryKey,
        updated,
      );
      toast.success(
        updated.auto_top_up.enabled
          ? "Auto top-up is on."
          : "Auto top-up is off.",
      );
      onOpenChange(false);
    },
    meta: { errorMessage: "Auto top-up could not be saved." },
  });

  const submit = () => {
    setTouched(true);
    if (!enabled || (thresholdValue !== null && amountValue !== null))
      save.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-md"
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Auto top-up</DialogTitle>
          <DialogDescription>
            Keep requests running by topping up before your balance runs out.
          </DialogDescription>
        </DialogHeader>

        <label className="flex cursor-pointer items-center justify-between rounded-lg border px-4 py-3">
          <span className="text-sm font-medium">Turn on auto top-up</span>
          <Switch
            aria-label="Turn on auto top-up"
            checked={enabled}
            onCheckedChange={setEnabled}
          />
        </label>

        <fieldset
          disabled={!enabled}
          className="grid grid-cols-2 gap-4 transition-opacity disabled:opacity-50"
        >
          <Field data-invalid={enabled && touched && thresholdValue === null}>
            <FieldLabel htmlFor="auto-top-up-threshold">
              When balance is below
            </FieldLabel>
            <UsdInput
              id="auto-top-up-threshold"
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
            />
            {enabled && touched && thresholdValue === null ? (
              <FieldError>Enter up to $10,000.</FieldError>
            ) : null}
          </Field>
          <Field data-invalid={enabled && touched && amountValue === null}>
            <FieldLabel htmlFor="auto-top-up-amount">Top up by</FieldLabel>
            <UsdInput
              id="auto-top-up-amount"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
            {enabled && touched && amountValue === null ? (
              <FieldError>Enter $5 to $10,000.</FieldError>
            ) : null}
          </Field>
        </fieldset>

        {account.payment_method ? (
          <SavedCardSummary
            card={account.payment_method}
            prefix="Charged to"
            className={cn("transition-opacity", !enabled && "opacity-50")}
          />
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={save.isPending} onClick={submit}>
            {save.isPending ? <LoaderCircle className="animate-spin" /> : null}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
