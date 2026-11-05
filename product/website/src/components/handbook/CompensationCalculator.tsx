import { useId, useState } from "react";
import type { ReactElement } from "react";
import compensation from "../../posthog-compensation.generated.json";

type Location = {
  country: string;
  area: string;
  locationFactor: number;
  currency?: string;
};

const benchmarks: Record<string, number> = compensation.benchmarks;
const steps: Record<string, number[]> = compensation.steps;
const currencies: Record<string, number> = compensation.currencies;
const locations: Location[] = compensation.locations;

const HIDDEN_LEVELS = new Set(["Director"]);
const levels = Object.entries(
  compensation.levels as Record<string, number>,
).filter(([level]) => !HIDDEN_LEVELS.has(level));

const countries = [...new Set(locations.map((l) => l.country))].sort();
const areasIn = (country: string): string[] =>
  locations
    .filter((l) => l.country === country)
    .map((l) => l.area)
    .sort();

const hasRate = (currency?: string): currency is string =>
  currency !== undefined && currencies[currency] !== undefined;

// Without a rate, show an unambiguous "USD" rather than a "$" that could be
// read as a local dollar or peso.
const formatPay = (usd: number, currency?: string): string =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: hasRate(currency) ? currency : "USD",
    currencyDisplay: hasRate(currency) ? "symbol" : "code",
    maximumFractionDigits: 0,
  }).format(Math.round(usd * (hasRate(currency) ? currencies[currency] : 1)));

const Select = ({
  label,
  value,
  options,
  display = (option) => option,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  display?: (option: string) => string;
  onChange: (value: string) => void;
}): ReactElement => {
  const id = useId();
  return (
    <div className="gr-field">
      <label className="gr-comp-calc__label" htmlFor={id}>
        {label}
      </label>
      <select
        className="gr-select"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {display(option)}
          </option>
        ))}
      </select>
    </div>
  );
};

export const CompensationCalculator = ({
  initialRole = "Product Engineer",
}: {
  initialRole?: string;
}): ReactElement => {
  const [role, setRole] = useState(
    benchmarks[initialRole] ? initialRole : Object.keys(benchmarks)[0],
  );
  const [country, setCountry] = useState(
    countries.includes("United States") ? "United States" : countries[0],
  );
  const [area, setArea] = useState("San Francisco, California");
  const [level, setLevel] = useState(
    levels.some(([name]) => name === "Senior") ? "Senior" : levels[0][0],
  );
  const [step, setStep] = useState(
    steps.Established ? "Established" : Object.keys(steps)[0],
  );

  const location =
    locations.find((l) => l.country === country && l.area === area) ??
    locations.find((l) => l.country === country) ??
    locations[0];
  const levelModifier =
    levels.find(([name]) => name === level)?.[1] ?? levels[0][1];
  const [stepLow, stepHigh] = steps[step];
  const benchmark = benchmarks[role] * location.locationFactor;
  const pay = (stepModifier: number): string =>
    formatPay(benchmark * levelModifier * stepModifier, location.currency);

  return (
    <section
      aria-label="Compensation calculator"
      className="gr-comp-calc ph-no-capture"
    >
      <div className="gr-comp-calc__fields">
        <Select
          label="Role"
          onChange={setRole}
          options={Object.keys(benchmarks)}
          value={role}
        />
        <Select
          label="Country"
          onChange={(next) => {
            setCountry(next);
            setArea(areasIn(next)[0]);
          }}
          options={countries}
          value={country}
        />
        <Select
          label="Region"
          onChange={setArea}
          options={areasIn(country)}
          value={location.area}
        />
        <Select
          display={(name) =>
            `${name} (${levels.find(([n]) => n === name)?.[1]})`
          }
          label="Level"
          onChange={setLevel}
          options={levels.map(([name]) => name)}
          value={level}
        />
        <Select
          display={(name) => `${name} (${steps[name][0]} - ${steps[name][1]})`}
          label="Step"
          onChange={setStep}
          options={Object.keys(steps)}
          value={step}
        />
      </div>

      <dl className="gr-comp-calc__formula">
        <div>
          <dt>
            Benchmark ({location.country}, {location.area})
          </dt>
          <dd>{formatPay(benchmark, location.currency)}</dd>
        </div>
        <div>
          <dt>× Level</dt>
          <dd>{levelModifier}</dd>
        </div>
        <div>
          <dt>× Step</dt>
          <dd>
            {stepLow} - {stepHigh}
          </dd>
        </div>
        <div className="gr-comp-calc__total">
          <dt>Salary</dt>
          <dd>
            {pay(stepLow)} - {pay(stepHigh)}
            <span>plus equity</span>
          </dd>
        </div>
      </dl>

      {location.currency && !hasRate(location.currency) ? (
        <p className="gr-comp-calc__note">
          Shown in US dollars, because PostHog's data has no exchange rate for{" "}
          {location.currency}.
        </p>
      ) : null}

      {role.includes("Engineer") && role !== "Support Engineer" ? (
        <p className="gr-comp-calc__note">
          For exceptional engineers we'll go well beyond these ranges.
        </p>
      ) : null}
    </section>
  );
};
