import { Command as CommandPrimitive } from "cmdk";
import { Search } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Command = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive>) => (
  <CommandPrimitive
    className={cn(
      "flex w-full flex-col overflow-hidden rounded-md bg-popover text-popover-foreground",
      className,
    )}
    {...props}
  />
);

export const CommandInput = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.Input>) => (
  <div className="flex items-center border-b px-3" cmdk-input-wrapper="">
    <Search className="mr-2 size-4 shrink-0 opacity-50" />
    <CommandPrimitive.Input
      className={cn(
        "flex h-11 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  </div>
);

export const CommandList = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.List>) => (
  <CommandPrimitive.List
    className={cn(
      "max-h-72 overflow-x-hidden overflow-y-auto scroll-py-1",
      className,
    )}
    {...props}
  />
);

export const CommandEmpty = (
  props: ComponentProps<typeof CommandPrimitive.Empty>,
) => <CommandPrimitive.Empty className="py-6 text-center text-sm" {...props} />;

export const CommandGroup = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.Group>) => (
  <CommandPrimitive.Group
    className={cn("overflow-hidden p-1 text-foreground", className)}
    {...props}
  />
);

export const CommandItem = ({
  className,
  ...props
}: ComponentProps<typeof CommandPrimitive.Item>) => (
  <CommandPrimitive.Item
    className={cn(
      "relative flex cursor-default items-center gap-2 rounded-sm px-2 py-2 text-sm outline-none select-none data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50 data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground",
      className,
    )}
    {...props}
  />
);
