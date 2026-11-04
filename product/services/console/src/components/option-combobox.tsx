import { useId, useState, type ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";
import type { Option } from "@/components/option-select";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export const OptionCombobox = <Value extends string>({
  value,
  options,
  onValueChange,
  label,
  className,
  disabled,
  placeholder,
  renderOption,
}: {
  value: Value;
  options: readonly Option<Value>[];
  onValueChange: (value: Value) => void;
  label: string;
  className?: string;
  disabled?: boolean;
  placeholder?: string;
  renderOption?: (option: Option<Value>) => ReactNode;
}) => {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const selected = options.find((option) => option.value === value);
  const render = (option: Option<Value>) =>
    renderOption ? renderOption(option) : option.label;
  const groups = [...new Set(options.map((option) => option.group))];

  return (
    <Popover modal open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          disabled={disabled ?? false}
          className={cn("justify-between font-normal", className)}
        >
          {selected ? render(selected) : (placeholder ?? "Select a model")}
          <ChevronDown className="size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        id={listId}
        align="start"
        className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0"
      >
        <Command label={`Search ${label.toLowerCase()}`}>
          <CommandInput
            aria-label={`Search ${label.toLowerCase()}`}
            placeholder="Search models…"
          />
          <CommandList className="max-h-[min(18rem,var(--radix-popover-content-available-height))] overscroll-contain">
            <CommandEmpty>No models found.</CommandEmpty>
            {groups.map((group) => (
              <CommandGroup
                key={group ?? ""}
                {...(group ? { heading: group } : {})}
              >
                {options
                  .filter((option) => option.group === group)
                  .map((option) => (
                    <CommandItem
                      key={option.value}
                      value={option.value}
                      keywords={[option.label]}
                      disabled={option.disabled ?? false}
                      onSelect={() => {
                        onValueChange(option.value);
                        setOpen(false);
                      }}
                    >
                      {render(option)}
                      <Check
                        className={cn(
                          "ml-auto size-4 shrink-0",
                          value === option.value ? "opacity-100" : "opacity-0",
                        )}
                      />
                    </CommandItem>
                  ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};
