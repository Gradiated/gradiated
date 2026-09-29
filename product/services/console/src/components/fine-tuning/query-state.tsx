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
    <p role="status" className="p-4 text-sm text-muted-foreground">
      Loading training data…
    </p>
  ) : null;
