import { useState } from "react";
import type { FormEvent, ReactElement } from "react";

import { authClient } from "../../api/auth";
import { useDocsSession } from "./DocsSession";

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
    return <p className="m-0 text-[11px] text-muted">Checking account…</p>;
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
            className="cursor-pointer border-0 bg-transparent p-0 text-[10px] uppercase tracking-label text-muted hover:text-ink"
            disabled={signingOut}
            onClick={() => void signOut()}
            type="button"
          >
            {signingOut ? "Logging out…" : "Log out"}
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
      <label className="block text-[10px] uppercase tracking-label text-muted">
        Log in to create keys and run requests
      </label>
      <input
        className="mt-3 w-full border border-line bg-transparent px-3 py-2 font-libre text-[12px] text-ink outline-none focus:border-ink"
        id="docs-login-email"
        onChange={(event) => setEmail(event.target.value)}
        placeholder="you@company.com"
        required
        type="email"
        value={email}
      />
      <button
        className="mt-2 w-full cursor-pointer border border-ink bg-ink px-3 py-2 font-libre text-[10px] font-medium uppercase tracking-label text-paper hover:bg-transparent hover:text-ink"
        type="submit"
      >
        Email login link
      </button>
      <div className="mt-2 grid grid-cols-2 gap-2">
        <button
          className="cursor-pointer border border-line bg-transparent px-2 py-2 font-libre text-[10px] font-medium uppercase tracking-label text-ink hover:border-ink"
          onClick={() => void signInWith("github")}
          type="button"
        >
          GitHub
        </button>
        <button
          className="cursor-pointer border border-line bg-transparent px-2 py-2 font-libre text-[10px] font-medium uppercase tracking-label text-ink hover:border-ink"
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
