import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { stopImpersonation, type CurrentUser } from "@/api/queries";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/errors";
import { switchConsoleIdentity } from "@/lib/session-sync";

export const ImpersonationBanner = ({
  user,
}: {
  user: CurrentUser | undefined;
}) => {
  const stop = useMutation({
    mutationFn: stopImpersonation,
    onSuccess: () => {
      switchConsoleIdentity("/admin");
    },
    onError: (error) =>
      toast.error(
        errorMessage(
          error,
          "Could not return to your staff session. Sign in again.",
        ),
      ),
  });

  const [now, setNow] = useState(Date.now);
  const attemptedExpiry = useRef<string | null>(null);
  const deadline = user?.impersonation_expires_at;
  const remaining = deadline
    ? Math.max(0, Math.ceil((Date.parse(deadline) - now) / 1000))
    : null;

  useEffect(() => {
    if (!user?.impersonated_by || !deadline) return;

    const tick = () => setNow(Date.now());
    tick();
    const timer = setInterval(tick, 1000);
    window.addEventListener("focus", tick);
    document.addEventListener("visibilitychange", tick);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", tick);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [user?.impersonated_by, deadline]);

  useEffect(() => {
    if (
      user?.impersonated_by &&
      deadline &&
      remaining === 0 &&
      attemptedExpiry.current !== deadline
    ) {
      attemptedExpiry.current = deadline;
      stop.mutate();
    }
  }, [user?.impersonated_by, deadline, remaining, stop.mutate]);

  if (!user?.impersonated_by) return null;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-between gap-3 border-b bg-amber-100 px-5 py-3 text-sm text-amber-950"
    >
      <span>
        Viewing as <strong>{user.email}</strong>
        {remaining !== null && (
          <span
            className="ml-3 tabular-nums"
            role="timer"
            aria-label="Impersonation time remaining"
          >
            {Math.floor(remaining / 60)}:
            {String(remaining % 60).padStart(2, "0")} remaining
          </span>
        )}
      </span>
      <Button
        variant="outline"
        size="sm"
        disabled={stop.isPending}
        onClick={() => stop.mutate()}
      >
        Return to staff account
      </Button>
    </div>
  );
};
