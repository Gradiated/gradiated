import {
  Elements,
  PaymentElement,
  useElements,
  useStripe,
} from "@stripe/react-stripe-js";
import type { Appearance, Stripe } from "@stripe/stripe-js";
// The pure entry loads Stripe.js only when card entry opens, not on every page.
import { loadStripe } from "@stripe/stripe-js/pure";
import { useMutation } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import {
  createCardSetup,
  useSaveCard,
  type BillingAccount,
} from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// Stripe.js loads once per publishable key.
const stripes = new Map<string, Promise<Stripe | null>>();
const stripeFor = (publishableKey: string) => {
  const existing = stripes.get(publishableKey);
  if (existing) return existing;

  const loaded = loadStripe(publishableKey);
  stripes.set(publishableKey, loaded);

  return loaded;
};

// The Payment Element runs in Stripe's iframe, so it takes the console's tokens as values.
const appearance: Appearance = {
  theme: "stripe",
  variables: {
    colorPrimary: "#171714",
    colorText: "#171714",
    colorTextSecondary: "#686760",
    colorDanger: "#bb322b",
    colorBackground: "#ffffff",
    fontFamily: '"Inter Variable", Inter, system-ui, sans-serif',
    fontSizeBase: "14px",
    borderRadius: "6px",
    spacingUnit: "4px",
  },
  rules: {
    ".Input": { borderColor: "#d5d4cc", boxShadow: "none" },
    ".Input:focus": {
      borderColor: "#171714",
      boxShadow: "0 0 0 3px rgba(23, 23, 20, 0.12)",
    },
    ".Label": { fontWeight: "500" },
  },
};

export const CardDialog = ({
  account,
  open,
  onOpenChange,
}: {
  account: BillingAccount;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => {
  const organizationId = account.organization_id;
  const setup = useMutation({
    mutationFn: () => createCardSetup(organizationId),
    meta: { errorMessage: "Card entry could not be started." },
  });
  const { mutate, reset } = setup;

  // Each opening starts a new SetupIntent, so a closed attempt is never reused.
  useEffect(() => {
    if (open) mutate();
    else reset();
  }, [open, mutate, reset]);

  const replacing = Boolean(account.payment_method);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100svh-2rem)] max-w-md overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{replacing ? "Change card" : "Add card"}</DialogTitle>
          <DialogDescription>
            {replacing
              ? "The new card replaces the saved one for top-ups and auto top-up."
              : "The card is used for top-ups and auto top-up."}
          </DialogDescription>
        </DialogHeader>
        {setup.data ? (
          <Elements
            stripe={stripeFor(setup.data.publishable_key)}
            options={{ clientSecret: setup.data.client_secret, appearance }}
          >
            <CardForm
              organizationId={organizationId}
              onDone={() => onOpenChange(false)}
            />
          </Elements>
        ) : setup.isError ? (
          <div className="grid min-h-40 place-items-center">
            <Button variant="outline" onClick={() => setup.mutate()}>
              Try again
            </Button>
          </div>
        ) : (
          <CardFormSkeleton />
        )}
      </DialogContent>
    </Dialog>
  );
};

// Shaped like the Payment Element's card fields while Stripe loads.
const CardFormSkeleton = () => (
  <div aria-busy="true" aria-label="Loading card form" className="space-y-4">
    <div className="space-y-2">
      <Skeleton className="h-3.5 w-24" />
      <Skeleton className="h-10 w-full rounded-md" />
    </div>
    <div className="grid grid-cols-2 gap-3">
      {[0, 1].map((index) => (
        <div key={index} className="space-y-2">
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="h-10 w-full rounded-md" />
        </div>
      ))}
    </div>
    <div className="space-y-2">
      <Skeleton className="h-3.5 w-28" />
      <Skeleton className="h-10 w-full rounded-md" />
    </div>
  </div>
);

const CardForm = ({
  organizationId,
  onDone,
}: {
  organizationId: string;
  onDone: () => void;
}) => {
  const stripe = useStripe();
  const elements = useElements();
  const [ready, setReady] = useState(false);
  const save = useSaveCard(organizationId);

  // Stripe confirms the card in its iframe; a redirect, if one is needed,
  // returns to the billing page, which saves the card the same way.
  const confirm = useMutation({
    mutationFn: async () => {
      if (!stripe || !elements) throw new Error("Stripe is still loading.");

      const { error, setupIntent } = await stripe.confirmSetup({
        elements,
        redirect: "if_required",
        confirmParams: { return_url: `${window.location.origin}/billing` },
      });
      if (error) throw new Error(error.message ?? "The card was not saved.");

      return setupIntent.id;
    },
    meta: { errorMessage: "The card was not saved." },
    onSuccess: (setupIntentId) =>
      save.mutate(setupIntentId, { onSuccess: onDone }),
  });
  const pending = confirm.isPending || save.isPending;

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!pending) confirm.mutate();
  };

  return (
    <form onSubmit={submit} className="space-y-6">
      {ready ? null : <CardFormSkeleton />}
      {/* Mounted while hidden so Stripe can load it behind the skeleton. */}
      <div className={ready ? undefined : "h-0 overflow-hidden"}>
        <PaymentElement
          // Link's save-my-details form adds nothing to saving a card for top-ups.
          options={{ layout: "tabs", wallets: { link: "never" } }}
          onReady={() => setReady(true)}
        />
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={!ready || pending}>
          {pending ? <LoaderCircle className="animate-spin" /> : null}
          Save card
        </Button>
      </DialogFooter>
    </form>
  );
};
