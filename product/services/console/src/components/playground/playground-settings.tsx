import { ChevronRight } from "lucide-react";
import { useId, useState } from "react";

import type { ServiceTierPricingPolicy } from "@/api/queries";
import { ModelLabel } from "@/components/model-label";
import { OptionCombobox } from "@/components/option-combobox";
import { OptionSelect } from "@/components/option-select";
import { SegmentedControl } from "@/components/segmented-control";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  effectiveSettings,
  MODEL_SOURCE_LABEL,
  reasoningEfforts,
  supports,
  type PlaygroundModel,
  type PlaygroundSettings,
  type ParameterDescriptor,
  type PlaygroundSettingsPatch,
  type ServiceTier,
} from "@/lib/playground";

// What each tier trades for its usage multiplier.
const TIER_BENEFIT: Record<ServiceTier, string> = {
  flex: "Runs at lower priority, so replies can take longer.",
  default: "Balanced speed and cost.",
  fast: "Fastest replies: runs ahead of default and flex requests.",
};

export const PlaygroundSettingsPanel = ({
  models,
  loading,
  tiers,
  settings,
  onChange,
}: {
  models: readonly PlaygroundModel[];
  loading: boolean;
  tiers: readonly ServiceTierPricingPolicy[];
  settings: PlaygroundSettings;
  onChange: (patch: PlaygroundSettingsPatch) => void;
}) => {
  const systemPromptId = useId();
  const efforts = reasoningEfforts(settings.capabilities);
  const effective = effectiveSettings(settings);
  const { parameters, outputTokens } = settings.capabilities;
  const accepts = (name: string) => supports(parameters, name);
  const options = models.map((model) => ({
    value: model.id,
    label: model.label,
    group: MODEL_SOURCE_LABEL[model.source],
    disabled: !model.available,
  }));

  return (
    <div className="space-y-5">
      <Field>
        <span aria-hidden="true" className="text-sm leading-snug font-medium">
          Model
        </span>
        <OptionCombobox
          label="Model"
          className="w-full"
          value={settings.model}
          options={options}
          disabled={!options.length}
          placeholder={loading ? "Loading models…" : "No models available"}
          onValueChange={(model) => onChange({ model })}
          renderOption={(option) => (
            <ModelLabel
              id={models.find((model) => model.id === option.value)?.iconId}
              label={option.label}
            />
          )}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor={systemPromptId}>System prompt</FieldLabel>
        <Textarea
          id={systemPromptId}
          value={settings.systemPrompt}
          placeholder="You are a helpful assistant."
          className="max-h-64 min-h-24"
          onChange={(event) => onChange({ systemPrompt: event.target.value })}
        />
      </Field>
      {tiers.length > 1 ? (
        <ServiceTierPicker
          tiers={tiers}
          value={settings.serviceTier}
          onChange={(serviceTier) => onChange({ serviceTier })}
        />
      ) : null}
      {efforts.length ? (
        <Field>
          <span aria-hidden="true" className="text-sm leading-snug font-medium">
            Reasoning effort
          </span>
          <OptionSelect
            label="Reasoning effort"
            className="w-full"
            value={effective.reasoningEffort ?? ""}
            placeholder="Not set"
            options={efforts.map((effort) => ({
              value: effort,
              label: effort.charAt(0).toUpperCase() + effort.slice(1),
            }))}
            onValueChange={(reasoningEffort) => onChange({ reasoningEffort })}
          />
        </Field>
      ) : null}
      {accepts("temperature") ? (
        <ParameterInput
          key={`temperature-${settings.model}`}
          label="Temperature"
          value={effective.temperature}
          {...bounds(parameters.temperature)}
          step={0.1}
          onChange={(temperature) => onChange({ temperature })}
        />
      ) : null}
      <ParameterInput
        key={`max-tokens-${settings.model}`}
        label="Max tokens"
        value={effective.maxTokens}
        min={1}
        {...(outputTokens ? { max: outputTokens.max } : {})}
        step={1}
        onChange={(maxTokens) => onChange({ maxTokens })}
      />
      {accepts("top_p") ? (
        <ParameterInput
          key={`top-p-${settings.model}`}
          label="Top P"
          value={effective.topP}
          {...bounds(parameters.top_p)}
          step={0.05}
          onChange={(topP) => onChange({ topP })}
        />
      ) : null}
      <AdvancedParameters settings={settings} onChange={onChange} />
    </div>
  );
};

const ServiceTierPicker = ({
  tiers,
  value,
  onChange,
}: {
  tiers: readonly ServiceTierPricingPolicy[];
  value: ServiceTier;
  onChange: (tier: ServiceTier) => void;
}) => {
  const labelId = useId();
  const selected = tiers.find((tier) => tier.service_tier === value);
  const multiplier = selected
    ? selected.price_multiplier_numerator /
      selected.price_multiplier_denominator
    : 1;

  return (
    <Field>
      <span id={labelId} className="text-sm leading-snug font-medium">
        Service tier
      </span>
      <SegmentedControl
        labelledBy={labelId}
        className="w-full"
        value={value}
        options={tiers.map(({ service_tier: tier }) => ({
          value: tier,
          label: tier.charAt(0).toUpperCase() + tier.slice(1),
        }))}
        onValueChange={onChange}
      />
      <FieldDescription className="text-xs">
        <span className="font-medium text-foreground">
          {multiplier.toLocaleString()}× usage.
        </span>{" "}
        {TIER_BENEFIT[value]}
      </FieldDescription>
    </Field>
  );
};

// Bounds come from the catalog descriptor; an unbounded integer has no maximum.
const bounds = (
  descriptor: ParameterDescriptor | undefined,
): { min?: number; max?: number } =>
  descriptor?.type === "range" || descriptor?.type === "integer"
    ? {
        min: descriptor.min,
        ...(descriptor.max < Number.MAX_SAFE_INTEGER
          ? { max: descriptor.max }
          : {}),
      }
    : {};

// Optional parameters appear only for models whose catalog entry accepts them.
const AdvancedParameters = ({
  settings,
  onChange,
}: {
  settings: PlaygroundSettings;
  onChange: (patch: PlaygroundSettingsPatch) => void;
}) => {
  const stopId = useId();
  const jsonId = useId();
  const { parameters } = settings.capabilities;
  const effective = effectiveSettings(settings);
  const accepts = (name: string) => supports(parameters, name);

  if (
    ![
      "seed",
      "frequency_penalty",
      "presence_penalty",
      "stop",
      "response_format",
    ].some(accepts)
  ) {
    return null;
  }

  return (
    <details className="group space-y-5 border-t pt-4">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-sm font-medium [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-4 transition-transform group-open:rotate-90" />
        Advanced
      </summary>
      {accepts("frequency_penalty") ? (
        <ParameterInput
          key={`frequency-penalty-${settings.model}`}
          label="Frequency penalty"
          value={effective.frequencyPenalty}
          {...bounds(parameters.frequency_penalty)}
          step={0.1}
          onChange={(frequencyPenalty) => onChange({ frequencyPenalty })}
        />
      ) : null}
      {accepts("presence_penalty") ? (
        <ParameterInput
          key={`presence-penalty-${settings.model}`}
          label="Presence penalty"
          value={effective.presencePenalty}
          {...bounds(parameters.presence_penalty)}
          step={0.1}
          onChange={(presencePenalty) => onChange({ presencePenalty })}
        />
      ) : null}
      {accepts("seed") ? (
        <ParameterInput
          label="Seed"
          value={settings.seed}
          {...bounds(parameters.seed)}
          step={1}
          placeholder="Random"
          onChange={(seed) => onChange({ seed })}
        />
      ) : null}
      {accepts("stop") ? (
        <Field>
          <FieldLabel htmlFor={stopId}>Stop sequences</FieldLabel>
          <Textarea
            id={stopId}
            value={settings.stop}
            placeholder="One per line"
            className="min-h-16 font-mono text-xs"
            onChange={(event) => onChange({ stop: event.target.value })}
          />
        </Field>
      ) : null}
      {accepts("response_format") ? (
        <Field orientation="horizontal" className="justify-between">
          <FieldLabel htmlFor={jsonId}>JSON output</FieldLabel>
          <Switch
            id={jsonId}
            checked={settings.jsonOutput}
            onCheckedChange={(jsonOutput) => onChange({ jsonOutput })}
          />
        </Field>
      ) : null}
    </details>
  );
};

const ParameterInput = ({
  label,
  value,
  min,
  max,
  step,
  placeholder = "Not set",
  onChange,
}: {
  label: string;
  value: number | undefined;
  min?: number | undefined;
  max?: number | undefined;
  step: number;
  placeholder?: string;
  onChange: (value: number | undefined) => void;
}) => {
  const id = useId();
  // Text being typed shows as typed; otherwise the field follows the value,
  // which can change after mount when saved settings or the model load.
  const [draft, setDraft] = useState<string>();
  const outOfRange =
    value !== undefined &&
    ((min !== undefined && value < min) || (max !== undefined && value > max));
  const range =
    min === undefined
      ? max === undefined
        ? undefined
        : `Max ${bound(max)}`
      : max === undefined
        ? `Min ${bound(min)}`
        : `${bound(min)} to ${bound(max)}`;

  return (
    <Field data-invalid={outOfRange}>
      <div className="flex items-baseline justify-between gap-3">
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        {range ? (
          <span className="text-xs text-muted-foreground">{range}</span>
        ) : null}
      </div>
      <Input
        id={id}
        type="number"
        inputMode="decimal"
        {...(min === undefined ? {} : { min })}
        {...(max === undefined ? {} : { max })}
        step={step}
        value={draft ?? (value === undefined ? "" : String(value))}
        placeholder={placeholder}
        aria-invalid={outOfRange}
        onChange={(event) => {
          const next = event.target.valueAsNumber;

          setDraft(event.target.value);
          onChange(Number.isFinite(next) ? next : undefined);
        }}
        onBlur={() => setDraft(undefined)}
      />
    </Field>
  );
};

// A typographic minus keeps "−2 to 2" from reading as a hyphenated range.
const bound = (value: number) => value.toLocaleString().replace("-", "−");
