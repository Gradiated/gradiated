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
  ENGINEER_ONBOARDING_PATH,
  type VerifiedInstallation,
} from "@/lib/engineer-onboarding";

export const GITHUB_APP_INSTALL_URL =
  "https://github.com/apps/gradiated/installations/new";

export const GithubAppInstallation = ({
  organizationId,
  ndaDocumentId,
  saved,
  onVerified,
}: {
  organizationId: string;
  ndaDocumentId?: string | undefined;
  saved: VerifiedInstallation | null;
  onVerified: (installation: VerifiedInstallation | null) => void;
}) => {
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(false);
  const [status, setStatus] = useState(saved ? "installed" : "not_installed");
  const [installations, setInstallations] = useState<GithubInstallation[]>([]);
  const [selected, setSelected] = useState<VerifiedInstallation | null>(saved);
  const [error, setError] = useState("");
  const [authorizationUrl, setAuthorizationUrl] = useState("");
  const callback = useRef(onVerified);
  callback.current = onVerified;
  const savedInstallation = useRef(saved);
  const active = useRef(true);

  const check = useCallback(
    async (id?: number) => {
      setBusy(true);
      setError("");
      try {
        const result = await getGithubInstallations(organizationId, {
          ndaDocumentId,
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
      } finally {
        if (active.current) setBusy(false);
      }
    },
    [organizationId, ndaDocumentId],
  );

  useEffect(() => {
    active.current = true;
    void check(savedInstallation.current?.id);

    return () => {
      active.current = false;
    };
  }, [check]);

  useEffect(() => {
    if (!opened) return;

    const focus = () => {
      void check();
    };
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [opened, check]);

  const authorize = async () => {
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;

    setBusy(true);
    setError("");
    setOpened(true);
    try {
      const result = await authClient.linkSocial({
        provider: "github",
        callbackURL: new URL(
          `${ENGINEER_ONBOARDING_PATH}?organization=${organizationId}`,
          window.location.origin,
        ).toString(),
        disableRedirect: true,
      });
      if (result.error || !result.data?.url)
        throw new Error(result.error?.message ?? "Could not authorize GitHub.");

      const url = new URL(result.data.url);
      if (url.protocol !== "https:" || url.hostname !== "github.com")
        throw new Error("Unexpected GitHub authorization URL.");

      if (popup) popup.location.href = url.href;
      else setAuthorizationUrl(url.href);
    } catch (error) {
      popup?.close();
      setError(
        error instanceof Error ? error.message : "Could not authorize GitHub.",
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
      <Button asChild variant="outline" className="self-start">
        <a
          href={GITHUB_APP_INSTALL_URL}
          target="_blank"
          rel="noopener noreferrer"
          onClick={() => {
            setOpened(true);
            callback.current(null);
            setSelected(null);
          }}
        >
          Install GitHub app <ExternalLink />
        </a>
      </Button>
      {selected ? (
        <p role="status" className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="size-4 text-emerald-600" /> Installed ·{" "}
          {selected.account} · {selected.repository_count}{" "}
          {selected.repository_count === 1 ? "repository" : "repositories"}
        </p>
      ) : (
        <div className="flex flex-col items-start gap-2">
          {status === "authorization_required" ? (
            <Button
              type="button"
              variant="link"
              className="h-auto p-0"
              disabled={busy}
              onClick={() => void authorize()}
            >
              Authorize GitHub to verify installation
            </Button>
          ) : null}
          {authorizationUrl ? (
            <a
              className="text-sm underline underline-offset-4"
              href={authorizationUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open GitHub authorization
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
          <Button
            type="button"
            variant="link"
            className="h-auto p-0"
            disabled={busy}
            onClick={() => void check()}
          >
            {busy ? "Checking installation…" : "Check installation"}
          </Button>
          {opened && status === "not_installed" && !busy && !error ? (
            <p role="status" className="text-sm text-muted-foreground">
              Waiting for installation or organization-owner approval.
            </p>
          ) : null}
        </div>
      )}
      {error ? <FieldError>{error}</FieldError> : null}
    </section>
  );
};
