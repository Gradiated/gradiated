import { CheckCircle2, ExternalLink } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getGithubInstallations,
  type GithubInstallation,
} from "@/api/engineer-onboarding";
import { authClient } from "@/auth";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  GITHUB_RETURN_PATH,
  githubInstallUrl,
  type VerifiedInstallation,
} from "@/lib/engineer-onboarding";

const POLL_MS = 5000;

export const GithubAppInstallation = ({
  organizationId,
  saved,
  onVerified,
}: {
  organizationId: string;
  saved: VerifiedInstallation | null;
  onVerified: (installation: VerifiedInstallation | null) => void;
}) => {
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(false);
  const [status, setStatus] = useState(saved ? "installed" : "not_installed");
  const [installations, setInstallations] = useState<GithubInstallation[]>([]);
  const [selected, setSelected] = useState<VerifiedInstallation | null>(saved);
  const [error, setError] = useState("");
  const [installUrl, setInstallUrl] = useState("");
  const callback = useRef(onVerified);
  callback.current = onVerified;
  const savedInstallation = useRef(saved);
  const active = useRef(true);

  const check = useCallback(
    async (id?: number) => {
      setError("");
      try {
        const result = await getGithubInstallations(organizationId, {
          installationId: id,
        });
        if (!active.current) return;

        setStatus(result.status);
        setInstallations(result.installations);
        const chosen =
          result.installations.length === 1 ? result.installations[0]! : null;
        setSelected(chosen);
        callback.current(chosen);
      } catch (error) {
        if (active.current) {
          setSelected(null);
          callback.current(null);
          setError(
            error instanceof Error ? error.message : "Could not check GitHub.",
          );
        }
      }
    },
    [organizationId],
  );

  useEffect(() => {
    active.current = true;
    void check(savedInstallation.current?.id);

    return () => {
      active.current = false;
    };
  }, [check]);

  const waiting = opened && !selected && installations.length < 2;

  useEffect(() => {
    if (!waiting) return;

    const poll = () => {
      if (document.visibilityState === "visible") void check();
    };
    const timer = window.setInterval(poll, POLL_MS);
    window.addEventListener("focus", poll);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", poll);
    };
  }, [waiting, check]);

  const install = async () => {
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;

    setBusy(true);
    setError("");
    setInstallUrl("");
    setSelected(null);
    callback.current(null);
    try {
      const result = await authClient.linkSocial({
        provider: "github",
        callbackURL: new URL(
          GITHUB_RETURN_PATH,
          window.location.origin,
        ).toString(),
        disableRedirect: true,
      });
      if (result.error || !result.data?.url)
        throw new Error(
          result.error?.message ?? "Could not start the GitHub installation.",
        );

      const url = githubInstallUrl(result.data.url);
      setOpened(true);
      if (popup) popup.location.href = url;
      else setInstallUrl(url);
    } catch (error) {
      popup?.close();
      setError(
        error instanceof Error
          ? error.message
          : "Could not start the GitHub installation.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex flex-col gap-3 rounded-lg border p-4">
      <div>
        <h2 className="font-semibold">Install the Gradiated GitHub app</h2>
        <p className="text-sm text-muted-foreground">
          Choose which repositories we can access in GitHub.
        </p>
      </div>
      {selected ? (
        <p role="status" className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="size-4 text-emerald-600" /> Installed ·{" "}
          {selected.account} · {selected.repository_count}{" "}
          {selected.repository_count === 1 ? "repository" : "repositories"}
        </p>
      ) : (
        <div className="flex flex-col items-start gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void install()}
          >
            {opened ? "Open GitHub again" : "Install GitHub app"}{" "}
            <ExternalLink />
          </Button>
          {installUrl ? (
            <a
              className="text-sm underline underline-offset-4"
              href={installUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Continue to GitHub
            </a>
          ) : null}
          {installations.length > 1 ? (
            <Select onValueChange={(value) => void check(Number(value))}>
              <SelectTrigger
                aria-label="GitHub account"
                className="w-full sm:w-72"
              >
                <SelectValue placeholder="Choose the account you installed the app on" />
              </SelectTrigger>
              <SelectContent>
                {installations.map((item) => (
                  <SelectItem key={item.id} value={String(item.id)}>
                    {item.account}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
          {waiting && !error ? (
            <p role="status" className="text-sm text-muted-foreground">
              {status === "authorization_required"
                ? "Waiting for GitHub…"
                : "Waiting for GitHub. If an organization owner must approve the install, this updates once they do."}
            </p>
          ) : null}
        </div>
      )}
      {error ? <FieldError>{error}</FieldError> : null}
    </section>
  );
};
