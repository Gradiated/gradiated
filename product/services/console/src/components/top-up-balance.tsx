import { zodResolver } from "@hookform/resolvers/zod";
import { CreditCard, LoaderCircle } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { createTopUpCheckout } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { formatUsdShort } from "@/lib/format";

const TopUpFormSchema = z.object({
  amount: z
    .string()
    .trim()
    .regex(/^\d+(?:\.\d{1,2})?$/, "Enter a valid USD amount.")
    .refine((value) => {
      const amount = Number(value);
      return amount >= 5 && amount <= 10_000;
    }, "Enter an amount between $5 and $10,000."),
});

type TopUpFormValues = z.infer<typeof TopUpFormSchema>;

const dollarsToNanoUsd = (value: string) => {
  const [dollars = "0", cents = ""] = value.split(".");
  return (
    BigInt(dollars) * 1_000_000_000n +
    BigInt(cents.padEnd(2, "0")) * 10_000_000n
  ).toString();
};

export const TopUpBalance = ({
  organizationId,
}: {
  organizationId: string;
}) => {
  const form = useForm<TopUpFormValues>({
    resolver: zodResolver(TopUpFormSchema),
    defaultValues: { amount: "50" },
  });

  const submit = async (values: TopUpFormValues) => {
    try {
      const checkout = await createTopUpCheckout(
        organizationId,
        dollarsToNanoUsd(values.amount),
      );
      window.location.assign(checkout.checkout_url);
    } catch (error) {
      form.setError("root", {
        message:
          error instanceof Error
            ? error.message
            : "Stripe Checkout could not be started.",
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
        </div>
      </div>
      <form className="space-y-4" onSubmit={form.handleSubmit(submit)}>
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
              onClick={() => form.setValue("amount", String(amount))}
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
      </form>
    </section>
  );
};
