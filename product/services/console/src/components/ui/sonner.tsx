import {
  CircleCheck,
  CircleAlert,
  Info,
  Loader2,
  TriangleAlert,
} from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";

export const Toaster = (props: ToasterProps) => (
  <Sonner
    theme="light"
    position="bottom-right"
    className="toaster group"
    icons={{
      success: <CircleCheck className="size-4 text-[#6e7f31]" />,
      info: <Info className="size-4" />,
      warning: <TriangleAlert className="size-4" />,
      error: <CircleAlert className="size-4 text-destructive" />,
      loading: <Loader2 className="size-4 animate-spin" />,
    }}
    toastOptions={{
      unstyled: true,
      classNames: {
        toast:
          "flex w-full items-start gap-3 rounded-lg border border-border bg-card p-4 text-card-foreground shadow-lg font-sans",
        title: "text-sm font-medium",
        description: "mt-1 text-xs leading-5 text-muted-foreground",
        icon: "mt-0.5 shrink-0",
        content: "min-w-0 flex-1",
        actionButton:
          "shrink-0 self-center whitespace-nowrap rounded-md border border-border bg-background px-2.5 py-1.5 text-xs font-medium hover:bg-muted",
      },
    }}
    {...props}
  />
);
