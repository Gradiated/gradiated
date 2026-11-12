import { Clock, ExternalLink, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  getGithubInstallations,
  type GithubInstallation,
} from "@/api/engineer-onboarding";
import { authClient } from "@/auth";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field";
import {
  GITHUB_RETURN_PATH,
  githubInstallUrl,
  repositoryCount,
} from "@/lib/engineer-onboarding";
import { cn } from "@/lib/utils";

const POLL_MS = 5000;
const ACCOUNTS_SHOWN = 4;

const choose = (
  installations: GithubInstallation[],
  selectedId: number | null,
) =>
  installations.find((item) => item.id === selectedId) ??
  (installations.length === 1 ? installations[0]! : null);

export const GithubAppInstallation = ({
  organizationId,
  selectedId,
  onChange,
}: {
  organizationId: string;
  selectedId: number | null;
  onChange: (installation: GithubInstallation | null, accounts: number) => void;
}) => {
  const [installations, setInstallations] = useState<
    GithubInstallation[] | null
  >(null);
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [installUrl, setInstallUrl] = useState("");
  const [allAccounts, setAllAccounts] = useState(false);
  const callback = useRef(onChange);
  callback.current = onChange;
  const selected = useRef(selectedId);
  selected.current = selectedId;

  const check = useCallback(async () => {
    try {
      const result = await getGithubInstallations(organizationId);
      setError("");
      setInstallations(result.installations);
      callback.current(
        choose(result.installations, selected.current),
        result.installations.length,
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not check GitHub.",
      );
    }
  }, [organizationId]);

  useEffect(() => {
    void check();
  }, [check]);

  const chosen = installations ? choose(installations, selectedId) : null;
  /* Keep checking while GitHub may still change: after opening the install
     page, and while the chosen installation has no repositories. */
  const waiting =
    (opened && !chosen && (installations?.length ?? 0) < 2) ||
    chosen?.repository_count === 0;

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === "visible") void check();
    };
    window.addEventListener("focus", refresh);
    const timer = waiting ? window.setInterval(refresh, POLL_MS) : undefined;
    return () => {
      window.removeEventListener("focus", refresh);
      window.clearInterval(timer);
    };
  }, [waiting, check]);

  const install = async () => {
    const popup = window.open("about:blank", "_blank");
    if (popup) popup.opener = null;

    setBusy(true);
    setError("");
    setInstallUrl("");
    try {
      const returnUrl = new URL(
        GITHUB_RETURN_PATH,
        window.location.origin,
      ).toString();
      const result = await authClient.linkSocial({
        provider: "github",
        callbackURL: returnUrl,
        errorCallbackURL: returnUrl,
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
    } catch (cause) {
      popup?.close();
      setError(
        cause instanceof Error
          ? cause.message
          : "Could not start the GitHub installation.",
      );
    } finally {
      setBusy(false);
    }
  };

  const several = (installations?.length ?? 0) > 1;
  const accounts =
    installations && (allAccounts || installations.length <= ACCOUNTS_SHOWN + 1)
      ? installations
      : (installations?.slice(0, ACCOUNTS_SHOWN) ?? []);

  return (
    <div className="flex flex-col gap-4">
      {installations === null && !error ? (
        <p role="status" className="text-sm text-muted-foreground">
          Checking GitHub…
        </p>
      ) : null}
      {installations?.length === 0 ? (
        <>
          <p className="text-sm leading-6 text-muted-foreground">
            Install the Gradiated GitHub app on the repositories your researcher
            should work in. It shows up here as soon as GitHub confirms it.
          </p>
          {opened ? (
            <div
              role="status"
              className="flex gap-3 rounded-lg bg-muted p-4 text-sm"
            >
              <Clock className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span className="flex flex-col gap-1">
                <span className="font-medium">Waiting for GitHub…</span>
                <span className="text-muted-foreground">
                  If your GitHub organization needs an owner to approve the app,
                  ask them to. This updates by itself, so you can leave and come
                  back.
                </span>
              </span>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-4">
            <Button
              type="button"
              variant={opened ? "outline" : "default"}
              disabled={busy}
              onClick={() => void install()}
            >
              {opened ? "Open GitHub again" : "Install GitHub app"}
              <ExternalLink />
            </Button>
            {installUrl ? (
              <a
                className="text-sm font-medium underline underline-offset-4"
                href={installUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Continue to GitHub
              </a>
            ) : null}
          </div>
        </>
      ) : null}
      {several ? (
        <fieldset className="flex flex-col overflow-hidden rounded-lg border">
          <legend className="sr-only">GitHub account</legend>
          <p className="border-b px-4 py-3 text-sm text-muted-foreground">
            The Gradiated app is installed on {installations!.length} accounts
            you can see. Which one is this project for?
          </p>
          {accounts.map((item) => (
            <label
              key={item.id}
              className={cn(
                "flex min-h-14 cursor-pointer items-center gap-3 border-b px-4 py-2 last:border-b-0",
                item.id === chosen?.id && "bg-muted",
              )}
            >
              <input
                type="radio"
                name="github-account"
                className="accent-primary"
                checked={item.id === chosen?.id}
                onChange={() => callback.current(item, installations!.length)}
              />
              <AccountAvatar account={item.account} />
              <span className="flex-1 text-sm">
                <span className="font-medium">{item.account}</span>{" "}
                <span className="text-muted-foreground">
                  ·{" "}
                  {item.repository_count
                    ? repositoryCount(item.repository_count)
                    : "no repositories"}
                </span>
              </span>
              <span className="text-xs text-muted-foreground">
                {item.account_type === "User" ? "Personal" : "Organization"}
              </span>
            </label>
          ))}
          {accounts.length < installations!.length ? (
            <button
              type="button"
              className="min-h-11 border-t text-sm font-medium"
              onClick={() => setAllAccounts(true)}
            >
              Show {installations!.length - accounts.length} more
            </button>
          ) : null}
        </fieldset>
      ) : null}
      {chosen ? <InstallationCard installation={chosen} /> : null}
      {installations?.length ? (
        <button
          type="button"
          className="self-start text-sm text-muted-foreground underline underline-offset-4 disabled:opacity-50"
          disabled={busy}
          onClick={() => void install()}
        >
          Install on another GitHub account
        </button>
      ) : null}
      {error ? <FieldError>{error}</FieldError> : null}
    </div>
  );
};

const AccountAvatar = ({ account }: { account: string }) => (
  <span
    aria-hidden="true"
    className="grid size-9 shrink-0 place-items-center rounded-md bg-primary text-sm font-semibold uppercase text-primary-foreground"
  >
    {account.slice(0, 1)}
  </span>
);

const InstallationCard = ({
  installation,
}: {
  installation: GithubInstallation;
}) => {
  const empty = installation.repository_count === 0;
  const more = installation.repository_count - installation.repositories.length;

  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="flex flex-wrap items-center gap-3 p-4">
        <AccountAvatar account={installation.account} />
        <span className="flex min-w-48 flex-1 flex-col gap-0.5">
          <span className="font-medium">{installation.account}</span>
          <span
            role="status"
            className="flex items-center gap-1.5 text-sm text-muted-foreground"
          >
            {empty ? (
              <TriangleAlert className="size-3.5 text-amber-600" />
            ) : (
              <span
                aria-hidden="true"
                className="size-2 rounded-full bg-emerald-600"
              />
            )}
            Gradiated app installed ·{" "}
            {empty
              ? "no repositories selected"
              : installation.repository_selection === "all"
                ? `all ${repositoryCount(installation.repository_count)}`
                : repositoryCount(installation.repository_count)}
          </span>
        </span>
        <a
          className="text-sm font-medium underline underline-offset-4"
          href={installation.manage_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {empty ? "Choose repositories" : "Manage on GitHub"}
        </a>
      </div>
      {empty ? (
        <p className="border-t px-4 py-3 text-sm text-muted-foreground">
          Select at least one repository on GitHub so your researcher has
          something to work in. This updates by itself.
        </p>
      ) : (
        <ul
          aria-label={`Repositories in ${installation.account}`}
          className="border-t py-1 font-mono text-[13px]"
        >
          {installation.repositories.map((name) => (
            <li key={name} className="px-4 py-1.5">
              {name}
            </li>
          ))}
          {more > 0 ? (
            <li className="px-4 py-1.5 font-sans text-sm text-muted-foreground">
              and {more} more
            </li>
          ) : null}
        </ul>
      )}
    </div>
  );
};
