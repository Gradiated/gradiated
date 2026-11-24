import { useId, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
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

export type MultiOption = { value: string; label: string; count?: number };

export const MultiCombobox = ({
  label,
  options,
  value,
  onValueChange,
  className,
}: {
  label: string;
  options: readonly MultiOption[];
  value: ReadonlySet<string>;
  onValueChange: (value: ReadonlySet<string>) => void;
  className?: string;
}) => {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const chosen = options.filter((option) => value.has(option.value));
  const toggle = (option: string) => {
    const next = new Set(value);
    if (!next.delete(option)) next.add(option);
    onValueChange(next);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          className={cn(
            "h-8 justify-between gap-1.5 font-normal",
            !chosen.length && "text-muted-foreground",
            className,
          )}
        >
          <span className="truncate">
            {label}
            {chosen.length === 1 ? (
              <span className="text-foreground">: {chosen[0]!.label}</span>
            ) : chosen.length > 1 ? (
              <span className="text-foreground"> · {chosen.length}</span>
            ) : null}
          </span>
          <ChevronDown className="size-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent id={listId} align="start" className="w-56 p-0">
        <Command label={`Filter by ${label.toLowerCase()}`}>
          <CommandInput
            aria-label={`Search ${label.toLowerCase()}`}
            placeholder={`Search ${label.toLowerCase()}…`}
          />
          <CommandList className="max-h-[min(18rem,var(--radix-popover-content-available-height))] overscroll-contain">
            <CommandEmpty>No matches.</CommandEmpty>
            <CommandGroup>
              {options.map((option) => {
                const selected = value.has(option.value);

                return (
                  <CommandItem
                    key={option.value}
                    value={option.value}
                    keywords={[option.label]}
                    onSelect={() => toggle(option.value)}
                  >
                    <span
                      className={cn(
                        "flex size-4 shrink-0 items-center justify-center rounded-[4px] border",
                        selected &&
                          "border-primary bg-primary text-primary-foreground",
                      )}
                    >
                      {selected ? <Check className="size-3" /> : null}
                    </span>
                    <span className="truncate">{option.label}</span>
                    {option.count !== undefined ? (
                      <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                        {option.count}
                      </span>
                    ) : null}
                  </CommandItem>
                );
              })}
            </CommandGroup>
          </CommandList>
          {chosen.length ? (
            <button
              type="button"
              onClick={() => onValueChange(new Set())}
              className="border-t px-3 py-2 text-left text-xs text-muted-foreground hover:text-foreground"
            >
              Clear
            </button>
          ) : null}
        </Command>
      </PopoverContent>
    </Popover>
  );
};
