import type { ReactNode } from "react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export interface Option<Value extends string> {
  value: Value;
  label: string;
  disabled?: boolean;
}

const findOption = <Value extends string>(
  options: readonly Option<Value>[],
  value: string,
): Value | undefined => options.find((option) => option.value === value)?.value;

const optionHandler =
  <Value extends string>(
    options: readonly Option<Value>[],
    onValueChange: (value: Value) => void,
  ) =>
  (next: string) => {
    const option = findOption(options, next);
    if (option !== undefined) onValueChange(option);
  };

export const OptionSelect = <Value extends string>({
  value,
  options,
  onValueChange,
  label,
  className,
  itemClassName,
  disabled,
  placeholder,
}: {
  value: Value;
  options: readonly Option<Value>[];
  onValueChange: (value: Value) => void;
  label: string;
  className?: string;
  itemClassName?: string;
  disabled?: boolean;
  placeholder?: string;
}) => (
  <Select
    disabled={disabled ?? false}
    value={value}
    onValueChange={optionHandler(options, onValueChange)}
  >
    <SelectTrigger className={className} aria-label={label}>
      <SelectValue placeholder={placeholder} />
    </SelectTrigger>
    <SelectContent>
      {options.map((option) => (
        <SelectItem
          key={option.value}
          value={option.value}
          disabled={option.disabled ?? false}
          className={itemClassName}
        >
          {option.label}
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
);

export const OptionTabs = <Value extends string>({
  value,
  options,
  onValueChange,
  children,
}: {
  value: Value;
  options: readonly Option<Value>[];
  onValueChange: (value: Value) => void;
  children: ReactNode;
}) => (
  <Tabs value={value} onValueChange={optionHandler(options, onValueChange)}>
    <TabsList>
      {options.map((option) => (
        <TabsTrigger key={option.value} value={option.value}>
          {option.label}
        </TabsTrigger>
      ))}
    </TabsList>
    {children}
  </Tabs>
);
