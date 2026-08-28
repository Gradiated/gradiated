import { useState } from "react";
import type { FormEvent, ReactElement } from "react";

import { authClient } from "../../api/auth";
import { useDocsSession } from "./DocsSession";

const loginLabelClass =
  "block min-h-[28px] text-[10px] uppercase tracking-label text-muted";
const loginInputClass =
  "mt-3 h-[34px] w-full border border-line px-3 font-libre text-[12px] text-ink outline-none focus:border-ink";
const loginPrimaryButtonClass =
  "mt-2 h-[34px] w-full border border-ink px-3 font-libre text-[10px] font-medium uppercase tracking-label";
const loginSocialButtonClass =
  "h-[34px] border border-line px-2 font-libre text-[10px] font-medium uppercase tracking-label";

const LogoutSpinner = (): ReactElement => (
  <svg
    aria-hidden="true"
    className="mx-auto h-3.5 w-3.5 animate-spin"
    fill="none"
    viewBox="0 0 16 16"
  >
    <circle
      className="opacity-25"
      cx="8"
      cy="8"
      r="6"
      stroke="currentColor"
      strokeWidth="2"
    />
    <path
      className="opacity-80"
      d="M8 2a6 6 0 0 1 6 6"
      stroke="currentColor"
      strokeLinecap="round"
      strokeWidth="2"
    />
  </svg>
);

const DocsAccountSkeleton = (): ReactElement => (
  <div
    aria-label="Loading account"
    aria-live="polite"
    className="border-b border-line pb-6"
    role="status"
  >
    <div aria-hidden="true" className="animate-pulse">
      <div className={`${loginLabelClass} relative`}>
        <span className="invisible">
          Log in to create keys and run requests
        </span>
        <span className="absolute left-0 top-0.5 h-2 w-[88%] bg-line" />
        <span className="absolute left-0 top-[17px] h-2 w-[48%] bg-line" />
      </div>
      <div className={`${loginInputClass} bg-line`} />
      <div className="mt-2 h-[34px] w-full bg-line" />
      <div className="mt-2 grid grid-cols-2 gap-2">
        <div className="h-[34px] bg-line" />
        <div className="h-[34px] bg-line" />
      </div>
    </div>
  </div>
);

export const DocsAccount = (): ReactElement => {
  const session = useDocsSession();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  const sendMagicLink = async (
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    event.preventDefault();
    setError(null);
    const result = await authClient.signIn.magicLink({
      email,
      callbackURL: window.location.href,
    });
    if (result.error) {
      setError(result.error.message ?? "The login link could not be sent.");
      return;
    }
    setSent(true);
  };

  const signOut = async (): Promise<void> => {
    setError(null);
    setSigningOut(true);
    try {
      const result = await authClient.signOut();
      if (result.error) {
        setError(result.error.message ?? "Logout failed.");
        return;
      }
      await session.refresh();
    } catch {
      setError("Logout failed. Try again.");
    } finally {
      setSigningOut(false);
    }
  };

  const signInWith = async (provider: "github" | "google"): Promise<void> => {
    setError(null);
    const result = await authClient.signIn.social({
      provider,
      callbackURL: window.location.href,
      newUserCallbackURL: window.location.href,
    });
    if (result?.error) {
      setError(result.error.message ?? "Login could not start.");
    }
  };

  if (session.status === "loading") {
    return <DocsAccountSkeleton />;
  }

  if (session.status === "ready" && session.user) {
    return (
      <div className="border-b border-line pb-6">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="m-0 truncate text-[11px] text-ink">
              {session.user.email}
            </p>
            <p className="mt-1 truncate text-[10px] text-muted">
              {session.workspace?.name ?? "No workspace"}
            </p>
          </div>
          <button
            aria-label={signingOut ? "Logging out" : "Log out"}
            className="h-5 w-[52px] shrink-0 cursor-pointer border-0 bg-transparent p-0 text-[10px] uppercase tracking-label text-muted hover:text-ink"
            disabled={signingOut}
            onClick={() => void signOut()}
            type="button"
          >
            {signingOut ? <LogoutSpinner /> : "Log out"}
          </button>
        </div>
        {session.user.organizations.length > 1 && session.organization && (
          <select
            aria-label="Organization"
            className="mt-3 w-full border border-line bg-transparent px-2 py-1.5 text-[10px] text-ink outline-none focus:border-ink"
            onChange={(event) =>
              void session.selectOrganization(event.target.value)
            }
            value={session.organization.id}
          >
            {session.user.organizations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        )}
        {session.workspaces.length > 1 && session.workspace && (
          <select
            aria-label="Workspace"
            className="mt-2 w-full border border-line bg-transparent px-2 py-1.5 text-[10px] text-ink outline-none focus:border-ink"
            onChange={(event) => session.selectWorkspace(event.target.value)}
            value={session.workspace.id}
          >
            {session.workspaces.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        )}
        {error && <p className="mt-2 text-[10px] text-earth">{error}</p>}
      </div>
    );
  }

  if (session.status === "error") {
    return (
      <div className="border-b border-line pb-6 text-[11px] leading-5 text-muted">
        <p className="m-0">Could not load your account.</p>
        <button
          className="mt-2 cursor-pointer border-0 bg-transparent p-0 text-[10px] uppercase tracking-label text-ink underline underline-offset-4"
          onClick={() => void session.refresh()}
          type="button"
        >
          Try again
        </button>
      </div>
    );
  }

  if (sent) {
    return (
      <div className="border-b border-line pb-6 text-[11px] leading-5 text-muted">
        Check your email. The link returns to this page.
      </div>
    );
  }

  return (
    <form className="border-b border-line pb-6" onSubmit={sendMagicLink}>
      <label className={loginLabelClass}>
        Log in to create keys and run requests
      </label>
      <input
        className={`${loginInputClass} bg-transparent`}
        id="docs-login-email"
        onChange={(event) => setEmail(event.target.value)}
        placeholder="you@company.com"
        required
        type="email"
        value={email}
      />
      <button
        className={`${loginPrimaryButtonClass} cursor-pointer bg-ink text-paper hover:bg-transparent hover:text-ink`}
        type="submit"
      >
        Email login link
      </button>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <button
          className={`${loginSocialButtonClass} cursor-pointer bg-transparent text-ink hover:border-ink`}
          onClick={() => void signInWith("github")}
          type="button"
        >
          GitHub
        </button>
        <button
          className={`${loginSocialButtonClass} cursor-pointer bg-transparent text-ink hover:border-ink`}
          onClick={() => void signInWith("google")}
          type="button"
        >
          Google
        </button>
      </div>
      {error && (
        <p className="mt-2 text-[10px] leading-4 text-earth">{error}</p>
      )}
    </form>
  );
};
