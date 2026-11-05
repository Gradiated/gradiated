import { useCallback, useEffect, useRef, useState } from "react";
import { createAuthClient } from "better-auth/react";
import { CheckCircle2, ExternalLink } from "lucide-react";
import { getGithubInstallations } from "../api/github";
import { productApiBaseUrl } from "../api/client";
import type { components } from "../api/schema";

export type GithubInstallation = components["schemas"]["GithubInstallation"];
const authClient = createAuthClient({ baseURL: productApiBaseUrl });

export const GithubAppInstall = ({
  organizationId,
  ndaDocumentId,
  demo,
  company,
  onVerified,
}: {
  organizationId: string;
  ndaDocumentId: string | null;
  demo: boolean;
  company: string;
  onVerified: (installation: GithubInstallation | null) => void;
}) => {
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(false);
  const [status, setStatus] = useState("not_installed");
  const [installations, setInstallations] = useState<GithubInstallation[]>([]);
  const [selected, setSelected] = useState<GithubInstallation | null>(null);
  const [error, setError] = useState("");
  const [authorizationUrl, setAuthorizationUrl] = useState("");
  const callback = useRef(onVerified);
  callback.current = onVerified;
  const active = useRef(true);

  const check = useCallback(
    async (id?: number) => {
      callback.current(null);
      if (demo || !ndaDocumentId) return;

      setBusy(true);
      setError("");
      try {
        const result = await getGithubInstallations(
          organizationId,
          ndaDocumentId,
          id,
        );
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
          setError(
            error instanceof Error ? error.message : "Could not check GitHub.",
          );
        }
      } finally {
        if (active.current) setBusy(false);
      }
    },
    [organizationId, ndaDocumentId, demo],
  );

  useEffect(() => {
    active.current = true;
    callback.current(null);
    if (!demo) void check();

    return () => {
      active.current = false;
    };
  }, [check, demo]);

  useEffect(() => {
    if (!opened || demo) return;

    const focus = () => {
      void check();
    };
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [opened, demo, check]);

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
          <CheckCircle2 size={16} /> {demo ? "Preview: installed" : "Installed"}{" "}
          · {selected.account} · {selected.repository_count}{" "}
          {selected.repository_count === 1 ? "repository" : "repositories"}
        </p>
      ) : demo ? (
        <>
          <button
            type="button"
            className="gs-text-button"
            onClick={() => {
              const installation = {
                id: 1,
                account: company,
                repository_count: 1,
              };
              setSelected(installation);
              callback.current(installation);
            }}
          >
            Simulate completed installation
          </button>
          <p className="gs-note">
            Installation checks are simulated in this preview.
          </p>
        </>
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
