import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import {
  resetIdentityState,
  sessionRevision,
  sessionChannel,
  SESSION_REVISION_KEY,
  SESSION_SOURCE,
} from "@/lib/session-sync";

export const SessionSync = () => {
  const client = useQueryClient();

  useEffect(() => {
    const revision = sessionRevision();
    const channel = sessionChannel();
    let reloading = false;
    const reload = () => {
      if (reloading) return;

      reloading = true;
      try {
        client.clear();
        resetIdentityState();
      } finally {
        window.location.reload();
      }
    };
    const synchronize = () => {
      if (sessionRevision() !== revision) reload();
    };
    const broadcastChanged = (event: MessageEvent<unknown>) => {
      if (typeof event.data === "string" && event.data !== SESSION_SOURCE)
        reload();
    };
    channel?.addEventListener("message", broadcastChanged);
    const storageChanged = (event: StorageEvent) => {
      if (event.key === SESSION_REVISION_KEY) synchronize();
    };
    const becameVisible = () => {
      if (document.visibilityState === "visible") synchronize();
    };
    window.addEventListener("storage", storageChanged);
    window.addEventListener("focus", synchronize);
    document.addEventListener("visibilitychange", becameVisible);

    return () => {
      channel?.close();
      window.removeEventListener("storage", storageChanged);
      window.removeEventListener("focus", synchronize);
      document.removeEventListener("visibilitychange", becameVisible);
    };
  }, [client]);

  return null;
};
