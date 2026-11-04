import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";

import { State, States } from "@/stories/states";
import {
  Field,
  FieldContent,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "./field";
import { Input } from "./input";
import { Switch } from "./switch";

const meta = { title: "Components/Field" } satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const States_: Story = {
  name: "States",
  render: () => (
    <States className="grid-cols-[repeat(auto-fill,minmax(18rem,1fr))]">
      <State label="Label only">
        <Field>
          <FieldLabel htmlFor="field-name">Workspace name</FieldLabel>
          <Input id="field-name" defaultValue="Production" />
        </Field>
      </State>
      <State label="With description">
        <Field>
          <FieldLabel htmlFor="field-threshold">Threshold</FieldLabel>
          <Input id="field-threshold" defaultValue="10" />
          <FieldDescription>
            Top up when your balance falls below this amount.
          </FieldDescription>
        </Field>
      </State>
      <State label="Error">
        <Field data-invalid>
          <FieldLabel htmlFor="field-amount">Amount</FieldLabel>
          <Input id="field-amount" aria-invalid defaultValue="2" />
          <FieldError>Enter an amount between $5 and $10,000.</FieldError>
        </Field>
      </State>
      <State label="Disabled">
        <Field data-disabled>
          <FieldLabel htmlFor="field-disabled">Organization</FieldLabel>
          <Input id="field-disabled" disabled defaultValue="Acme" />
          <FieldDescription>
            Only admins can rename the organization.
          </FieldDescription>
        </Field>
      </State>
    </States>
  ),
};

const HorizontalField = () => {
  const [enabled, setEnabled] = useState(true);

  return (
    <Field orientation="horizontal">
      <FieldContent>
        <FieldLabel htmlFor="field-capture">Capture traces</FieldLabel>
        <FieldDescription>
          Store prompts and responses for 30 days.
        </FieldDescription>
      </FieldContent>
      <Switch
        id="field-capture"
        checked={enabled}
        onCheckedChange={setEnabled}
      />
    </Field>
  );
};

export const Horizontal: Story = {
  render: () => (
    <States className="grid-cols-[minmax(0,28rem)]">
      <HorizontalField />
    </States>
  ),
};

export const Fieldset: Story = {
  render: () => (
    <States className="grid-cols-[minmax(0,28rem)]">
      <FieldSet>
        <FieldLegend>Auto top-up</FieldLegend>
        <FieldDescription>
          Charge your saved card when the balance runs low.
        </FieldDescription>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="fieldset-threshold">
              When balance falls below
            </FieldLabel>
            <Input id="fieldset-threshold" defaultValue="10" />
          </Field>
          <Field>
            <FieldLabel htmlFor="fieldset-amount">Top up by</FieldLabel>
            <Input id="fieldset-amount" defaultValue="50" />
          </Field>
        </FieldGroup>
      </FieldSet>
    </States>
  ),
};
