import { Skeleton } from "@/components/ui/skeleton";

export const QueryState = ({
  query,
}: {
  query: { isPending: boolean; error: Error | null; refetch: () => unknown };
}) =>
  query.error ? (
    <p role="alert" className="p-4 text-sm text-destructive">
      Could not load training data. {query.error.message}{" "}
      <button
        className="underline"
        onClick={(event) => {
          event.stopPropagation();
          void query.refetch();
        }}
      >
        Retry
      </button>
    </p>
  ) : query.isPending ? (
    <div
      role="status"
      aria-label="Loading training data"
      className="space-y-3 p-4"
    >
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-36 w-full" />
      <Skeleton className="h-36 w-full" />
    </div>
  ) : null;
