import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { gradKeys, useGrad } from "@/hooks/use-grad";
import { lastEventSeq, mergeRunEvents } from "@/lib/grad/run-events";
import type { RunEvent } from "@/lib/grad/types";

const FLUSH_MS = 150;

const REFRESHING_EVENTS: ReadonlySet<RunEvent["type"]> = new Set([
  "phase",
  "checkpoint",
  "attempt",
  "completed",
]);

export type RunEventsState = "connecting" | "live" | "finished" | "failed";

// Follows the run's SSE stream. Events stay in the query cache, so a remount
// or a retry resumes after the last seen event with Last-Event-ID.
export const useRunEvents = (runId: string) => {
  const { workspaceId, session, queryClient } = useGrad();
  const key = gradKeys.runEvents(workspaceId, runId);
  const [state, setState] = useState<RunEventsState>("connecting");
  const [error, setError] = useState<Error | null>(null);
  const [attempt, setAttempt] = useState(0);

  const events = useQuery({
    queryKey: key,
    queryFn: () => queryClient.getQueryData<RunEvent[]>(key) ?? [],
    staleTime: Infinity,
    gcTime: 10 * 60_000,
    enabled: Boolean(session && runId),
  });

  useEffect(() => {
    if (!session || !runId) return;

    const controller = new AbortController();
    let buffer: RunEvent[] = [];
    let timer: ReturnType<typeof setTimeout> | undefined;

    const flush = () => {
      timer = undefined;
      if (!buffer.length) return;

      const batch = buffer;
      buffer = [];
      queryClient.setQueryData<RunEvent[]>(key, (current = []) =>
        mergeRunEvents(current, batch),
      );

      if (batch.some((event) => REFRESHING_EVENTS.has(event.type))) {
        void queryClient.invalidateQueries({
          queryKey: gradKeys.run(workspaceId, runId),
        });
        void queryClient.invalidateQueries({
          queryKey: gradKeys.checkpoints(workspaceId, runId),
        });
      }
    };

    const follow = async () => {
      const after = lastEventSeq(
        queryClient.getQueryData<RunEvent[]>(key) ?? [],
      );
      setState("connecting");
      setError(null);

      for await (const event of session.grad.runs.events(runId, {
        follow: true,
        signal: controller.signal,
        ...(after ? { headers: { "Last-Event-ID": String(after) } } : {}),
      })) {
        setState("live");
        buffer.push(event);
        timer ??= setTimeout(flush, FLUSH_MS);
      }

      clearTimeout(timer);
      flush();
      setState("finished");
    };

    follow().catch((reason: unknown) => {
      if (controller.signal.aborted) return;

      clearTimeout(timer);
      flush();
      setError(reason instanceof Error ? reason : new Error(String(reason)));
      setState("failed");
    });

    return () => {
      controller.abort();
      clearTimeout(timer);
      flush();
    };
  }, [session, runId, workspaceId, queryClient, attempt]);

  return {
    events: events.data ?? [],
    state,
    error,
    retry: () => setAttempt((value) => value + 1),
  };
};
