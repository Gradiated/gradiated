import { useState } from "react";
import { OptionSelect } from "@/components/option-select";
import { Input } from "@/components/ui/input";

const weekdays = [
  { value: "SUN", label: "Sunday" },
  { value: "MON", label: "Monday" },
  { value: "TUE", label: "Tuesday" },
  { value: "WED", label: "Wednesday" },
  { value: "THU", label: "Thursday" },
  { value: "FRI", label: "Friday" },
  { value: "SAT", label: "Saturday" },
];
const timeOptions = (count: number) =>
  Array.from({ length: count }, (_, value) => ({
    value: String(value),
    label: String(value).padStart(2, "0"),
  }));
const hours = timeOptions(24);
const minutes = timeOptions(60);

const readSchedule = (value: string) => {
  const match =
    /^(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+(\*|[0-7]|SUN|MON|TUE|WED|THU|FRI|SAT)$/i.exec(
      value.trim(),
    );
  const [, minute, hour, weekday] = match ?? [];
  if (!minute || !hour || !weekday || Number(minute) > 59 || Number(hour) > 23)
    return null;

  const day = weekday.toUpperCase();
  return {
    minute: String(Number(minute)),
    hour: String(Number(hour)),
    day: /^\d$/.test(day) ? weekdays[Number(day) % 7]!.value : day,
  };
};

export const TrainingScheduleEditor = ({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) => {
  const [custom, setCustom] = useState(false);
  const parsed = readSchedule(value);
  const mode = custom
    ? "custom"
    : !value
      ? "manual"
      : parsed
        ? "scheduled"
        : "custom";
  const fields = parsed ?? { minute: "0", hour: "3", day: "*" };
  const changeField = (patch: Partial<typeof fields>) => {
    const next = { ...fields, ...patch };
    onChange(`${next.minute} ${next.hour} * * ${next.day}`);
  };
  const dayName = weekdays.find((day) => day.value === fields.day)?.label;

  return (
    <div className="space-y-3">
      <div className="flex flex-nowrap items-end gap-2 overflow-x-auto pb-1">
        <div className="shrink-0 space-y-1.5">
          <p className="text-xs text-muted-foreground">Schedule</p>
          <OptionSelect
            label="Training schedule"
            className="w-36"
            value={mode}
            disabled={disabled}
            onValueChange={(next) => {
              setCustom(next === "custom");
              if (next === "manual") onChange("");
              if (next === "scheduled" && !parsed) onChange("0 3 * * *");
            }}
            options={[
              { value: "manual", label: "Manual only" },
              { value: "scheduled", label: "Scheduled" },
              { value: "custom", label: "Custom cron" },
            ]}
          />
        </div>
        {mode === "scheduled" ? (
          <>
            <div className="shrink-0 space-y-1.5">
              <p className="text-xs text-muted-foreground">Hour</p>
              <OptionSelect
                label="Training hour"
                className="w-20 tabular-nums"
                value={fields.hour}
                disabled={disabled}
                options={hours}
                onValueChange={(hour) => changeField({ hour })}
              />
            </div>
            <div className="shrink-0 space-y-1.5">
              <p className="text-xs text-muted-foreground">Minute</p>
              <OptionSelect
                label="Training minute"
                className="w-20 tabular-nums"
                value={fields.minute}
                disabled={disabled}
                options={minutes}
                onValueChange={(minute) => changeField({ minute })}
              />
            </div>
            <div className="shrink-0 space-y-1.5">
              <p className="text-xs text-muted-foreground">Day</p>
              <OptionSelect
                label="Training day"
                className="w-36"
                value={fields.day}
                disabled={disabled}
                options={[{ value: "*", label: "Every day" }, ...weekdays]}
                onValueChange={(day) => changeField({ day })}
              />
            </div>
          </>
        ) : null}
      </div>
      {mode === "custom" ? (
        <div className="space-y-1.5">
          <Input
            aria-label="Cron schedule"
            className="font-mono text-sm"
            placeholder="0 3 * * MON"
            value={value}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Minute, hour, day of month, month, day of week. Times are in UTC.
          </p>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground" aria-live="polite">
          {mode === "manual"
            ? "Training runs only when you start it."
            : `Every ${dayName ?? "day"} at ${fields.hour.padStart(2, "0")}:${fields.minute.padStart(2, "0")} UTC.`}
        </p>
      )}
    </div>
  );
};
