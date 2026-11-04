import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import type { DateRange } from "react-day-picker";

import { State, States } from "@/stories/states";
import { Calendar } from "./calendar";

const month = new Date(2026, 10, 1);

const meta = { title: "Components/Calendar" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const Single = ({
  initial,
  disabledBefore,
}: {
  initial?: Date;
  disabledBefore?: Date;
}) => {
  const [date, setDate] = useState<Date | undefined>(initial);

  return (
    <Calendar
      mode="single"
      defaultMonth={month}
      selected={date}
      onSelect={setDate}
      {...(disabledBefore ? { disabled: { before: disabledBefore } } : {})}
      className="rounded-lg border"
    />
  );
};

const Range = () => {
  const [range, setRange] = useState<DateRange | undefined>({
    from: new Date(2026, 10, 9),
    to: new Date(2026, 10, 15),
  });

  return (
    <Calendar
      mode="range"
      defaultMonth={month}
      selected={range}
      onSelect={setRange}
      className="rounded-lg border"
    />
  );
};

export const States_: Story = {
  name: "States",
  render: () => (
    <States className="grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]">
      <State label="No selection">
        <Single />
      </State>
      <State label="Selected date">
        <Single initial={new Date(2026, 10, 20)} />
      </State>
      <State label="Past dates disabled">
        <Single disabledBefore={new Date(2026, 10, 12)} />
      </State>
      <State label="Range">
        <Range />
      </State>
    </States>
  ),
};
