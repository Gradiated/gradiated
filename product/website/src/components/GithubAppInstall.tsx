import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, ExternalLink } from "lucide-react";
import { getGithubInstallations } from "../api/github";
import { authClient } from "../api/auth";
import type { components } from "../api/schema";
import type { VerifiedInstallation } from "../onboarding";

type GithubInstallation = components["schemas"]["GithubInstallation"];

export const GithubAppInstall = ({
  organizationId,
  ndaDocumentId,
  saved,
  onVerified,
}: {
  organizationId: string;
  ndaDocumentId?: string;
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
        callbackURL: `${window.location.origin}/get-started/?github_authorized=1`,
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
    <div className="gs-github-install">
      <h2>Install the Gradiated GitHub app</h2>
      <p>Choose which repositories we can access in GitHub.</p>
      <a
        className="gr-button"
        href="https://github.com/apps/gradiated/installations/new"
        target="_blank"
        rel="noopener noreferrer"
        onClick={() => {
          setOpened(true);
          callback.current(null);
          setSelected(null);
        }}
      >
        Install GitHub app <ExternalLink size={14} />
      </a>
      {selected ? (
        <p role="status">
          <CheckCircle2 size={16} /> Installed · {selected.account} ·{" "}
          {selected.repository_count}{" "}
          {selected.repository_count === 1 ? "repository" : "repositories"}
        </p>
      ) : (
        <>
          {status === "authorization_required" && (
            <button
              type="button"
              className="gs-text-button"
              disabled={busy}
              onClick={() => void authorize()}
            >
              Authorize GitHub to verify installation
            </button>
          )}
          {authorizationUrl && (
            <a
              href={authorizationUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open GitHub authorization
            </a>
          )}
          {installations.length > 1 && (
            <label className="gs-field">
              <span>GitHub account</span>
              <select
                defaultValue=""
                onChange={(event) => void check(Number(event.target.value))}
              >
                <option value="" disabled>
                  Choose the account you installed the app on
                </option>
                {installations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.account}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            className="gs-text-button"
            disabled={busy}
            onClick={() => void check()}
          >
            {busy ? "Checking installation…" : "Check installation"}
          </button>
          {opened && status === "not_installed" && !busy && !error && (
            <p role="status" className="gs-note">
              Waiting for installation or organization-owner approval.
            </p>
          )}
        </>
      )}
      {error && (
        <p role="alert" className="gs-note">
          {error}
        </p>
      )}
    </div>
  );
};
