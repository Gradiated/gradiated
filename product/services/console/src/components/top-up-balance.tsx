import { analytics } from "@/lib/analytics";
import { zodResolver } from "@hookform/resolvers/zod";
import { CreditCard, LoaderCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createTopUpCheckout } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/errors";
import { formatUsdShort } from "@/lib/format";
import {
  MAX_TOP_UP_NANO_USD,
  MIN_TOP_UP_NANO_USD,
  NANO_USD_PER_USD,
  USD_AMOUNT_PATTERN,
  parseUsdToNanoUsd,
} from "@/lib/money";

const wholeUsd = (nanoUsd: bigint) =>
  formatUsdShort(Number(nanoUsd / NANO_USD_PER_USD));

const TopUpFormSchema = z.object({
  amount: z
    .string()
    .trim()
    .regex(USD_AMOUNT_PATTERN, "Enter a valid USD amount.")
    .transform(parseUsdToNanoUsd)
    .refine(
      (amount) =>
        amount >= MIN_TOP_UP_NANO_USD && amount <= MAX_TOP_UP_NANO_USD,
      `Enter an amount between ${wholeUsd(MIN_TOP_UP_NANO_USD)} and ${wholeUsd(MAX_TOP_UP_NANO_USD)}.`,
    ),
});

type TopUpFormInput = z.input<typeof TopUpFormSchema>;
type TopUpFormValues = z.output<typeof TopUpFormSchema>;

export const TopUpBalance = ({
  organizationId,
  disabled = false,
}: {
  organizationId: string;
  disabled?: boolean;
}) => {
  const form = useForm<TopUpFormInput, unknown, TopUpFormValues>({
    resolver: zodResolver(TopUpFormSchema),
    defaultValues: { amount: "50" },
  });

  const submit = async (values: TopUpFormValues) => {
    analytics.track("billing_top_up_clicked", {
      organization_id: organizationId,
    });
    try {
      const checkout = await createTopUpCheckout(
        organizationId,
        values.amount.toString(),
      );
      window.location.assign(checkout.checkout_url);
    } catch (error) {
      form.setError("root", {
        message: errorMessage(error, "Stripe Checkout could not be started."),
      });
    }
  };

  return (
    <section className="rounded-xl border bg-card p-5 shadow-sm">
      <div className="mb-5 flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
          <CreditCard className="size-4" />
        </span>
        <div>
          <h2 className="font-medium">Add funds</h2>
          {disabled ? (
            <p className="mt-0.5 text-sm text-muted-foreground">
              Only admins can add funds.
            </p>
          ) : null}
        </div>
      </div>
      <form onSubmit={form.handleSubmit(submit)}>
        <fieldset className="space-y-4" disabled={disabled}>
          <Field data-invalid={Boolean(form.formState.errors.amount)}>
            <FieldLabel htmlFor="top-up-amount">Amount (USD)</FieldLabel>
            <div className="relative">
              <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted-foreground">
                $
              </span>
              <Input
                id="top-up-amount"
                className="pl-7"
                inputMode="decimal"
                autoComplete="off"
                {...form.register("amount")}
              />
            </div>
            {form.formState.errors.amount ? (
              <FieldError errors={[form.formState.errors.amount]} />
            ) : null}
          </Field>
          <div className="grid grid-cols-4 gap-2">
            {[25, 50, 100, 250].map((amount) => (
              <Button
                key={amount}
                type="button"
                variant="outline"
                size="sm"
                onClick={() =>
                  form.setValue("amount", String(amount), {
                    shouldValidate: true,
                  })
                }
              >
                {formatUsdShort(amount)}
              </Button>
            ))}
          </div>
          {form.formState.errors.root?.message ? (
            <FieldError>{form.formState.errors.root.message}</FieldError>
          ) : null}
          <Button
            className="w-full"
            type="submit"
            disabled={form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : null}
            Continue to Stripe
          </Button>
        </fieldset>
      </form>
    </section>
  );
};
