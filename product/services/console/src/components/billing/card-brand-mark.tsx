import { CreditCard } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

const BRAND_NAMES: Record<string, string> = {
  amex: "American Express",
  cartes_bancaires: "Cartes Bancaires",
  diners: "Diners Club",
  discover: "Discover",
  eftpos_au: "eftpos",
  jcb: "JCB",
  mastercard: "Mastercard",
  unionpay: "UnionPay",
  visa: "Visa",
};

export const cardBrandName = (brand: string | null) =>
  (brand && BRAND_NAMES[brand]) ?? "Card";

const Wordmark = ({
  className,
  children,
}: {
  className?: string;
  children: string;
}) => (
  <span
    className={cn(
      "text-[9px] font-black leading-none tracking-tight text-white",
      className,
    )}
  >
    {children}
  </span>
);

const BrandArt = ({ brand }: { brand: string }) => {
  switch (brand) {
    case "visa":
      return <Wordmark className="italic">VISA</Wordmark>;
    case "mastercard":
      return (
        <span className="flex">
          <span className="size-3 rounded-full bg-[#eb001b]" />
          <span className="-ml-1.5 size-3 rounded-full bg-[#f79e1b] mix-blend-screen" />
        </span>
      );
    case "amex":
      return <Wordmark className="text-[8px]">AMEX</Wordmark>;
    case "discover":
      return (
        <span className="flex items-center gap-px">
          <Wordmark className="text-[7px] text-[#1d1d1b]">DISC</Wordmark>
          <span className="size-1.5 rounded-full bg-[#f58220]" />
        </span>
      );
    case "jcb":
      return <Wordmark>JCB</Wordmark>;
    case "unionpay":
      return <Wordmark className="text-[8px]">UP</Wordmark>;
    case "diners":
      return <Wordmark className="text-[8px]">DC</Wordmark>;
    default:
      return <CreditCard className="size-4 text-muted-foreground" />;
  }
};

const BRAND_BACKGROUND: Record<string, string> = {
  amex: "bg-[#006fcf]",
  diners: "bg-[#0079be]",
  discover: "bg-white ring-1 ring-border",
  jcb: "bg-[#0b4ea2]",
  mastercard: "bg-[#1d1d1b]",
  unionpay: "bg-[#d10429]",
  visa: "bg-[#1a1f71]",
};

export const CardBrandMark = ({
  brand,
  className,
}: {
  brand: string | null;
  className?: string;
}) => (
  <span
    role="img"
    aria-label={brand ? cardBrandName(brand) : "No card"}
    className={cn(
      "inline-grid h-6 w-9 shrink-0 place-items-center rounded-[5px]",
      (brand && BRAND_BACKGROUND[brand]) ?? "bg-muted",
      className,
    )}
  >
    <BrandArt brand={brand ?? ""} />
  </span>
);

// Details come from Stripe at read time; without them the card shows as on file.
export const cardLabel = (
  card: { brand: string | null; last4: string | null },
  style: "short" | "long" = "short",
) =>
  card.last4
    ? `${cardBrandName(card.brand)} ${style === "long" ? "ending in" : "••••"} ${card.last4}`
    : "Card on file";

// The muted strip that shows a saved card, or a stand-in, inside dialogs.
export const SavedCardSummary = ({
  card,
  prefix,
  className,
  children,
}: {
  card: { brand: string | null; last4: string | null } | null;
  prefix?: string;
  className?: string;
  children?: ReactNode;
}) => (
  <div
    className={cn(
      "flex items-center gap-3 rounded-lg bg-muted/60 px-4 py-3 text-sm",
      className,
    )}
  >
    {card ? (
      <>
        <CardBrandMark brand={card.brand} />
        {prefix ? `${prefix} ${cardLabel(card)}` : cardLabel(card)}
      </>
    ) : (
      <span className="text-muted-foreground">
        You&apos;ll enter your card details on Stripe.
      </span>
    )}
    {children}
  </div>
);
