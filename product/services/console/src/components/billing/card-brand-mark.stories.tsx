import type { Meta, StoryObj } from "@storybook/react-vite";

import { CardBrandMark, cardBrandName } from "./card-brand-mark";

const BRANDS = [
  "visa",
  "mastercard",
  "amex",
  "discover",
  "jcb",
  "unionpay",
  "diners",
  "unknown",
];

const meta = {
  title: "Pages/Billing/Blocks/Card brands",
  parameters: { layout: "fullscreen" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const CardBrands: Story = {
  name: "Card brands",
  render: () => (
    <div className="grid w-fit grid-cols-2 gap-x-8 gap-y-3 p-8">
      {BRANDS.map((brand) => (
        <div key={brand} className="flex items-center gap-3 text-sm">
          <CardBrandMark brand={brand} />
          {cardBrandName(brand)}
        </div>
      ))}
    </div>
  ),
};
