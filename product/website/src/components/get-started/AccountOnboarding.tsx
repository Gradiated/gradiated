import { useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { getCurrentUser } from "../../api/queries";
import type { CurrentUser } from "../../api/queries";
import { chooseAccount } from "../../onboarding";
import type { OnboardingAccount } from "../../onboarding";
import {
  ENGINEER_ORGANIZATION_SETUP_URL,
  ENGINEER_SIGNUP_URL,
} from "../../urls";
import { GetStartedWorkflow } from "./GetStartedWorkflow";
import { OnboardingHelp } from "./OnboardingParts";
import { OrganizationPicker } from "./OrganizationPicker";

export const AccountOnboarding = () => {
  const [organizations, setOrganizations] = useState<
    CurrentUser["organizations"]
  >([]);
  const [account, setAccount] = useState<OnboardingAccount | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError(false);

    void getCurrentUser()
      .then((user) => {
        if (!active) return;

        const choice = chooseAccount(
          user,
          new URLSearchParams(window.location.search).get("organization"),
        );
        if (choice.kind === "pick") setOrganizations(choice.organizations);
        else if (choice.kind === "missing") setError(true);
        else if (choice.kind === "ready") setAccount(choice.account);
        else {
          const destination = new URL(ENGINEER_ORGANIZATION_SETUP_URL);
          destination.searchParams.set("organization", choice.organizationId);
          window.location.replace(destination.toString());
        }
      })
      .catch((cause: unknown) => {
        if (!active) return;

        if (
          cause instanceof Error &&
          "status" in cause &&
          cause.status === 401
        ) {
          const recoverStaff =
            "code" in cause && cause.code === "staff_session_recovery_required";
          window.location.replace(
            recoverStaff
              ? ENGINEER_ORGANIZATION_SETUP_URL
              : ENGINEER_SIGNUP_URL,
          );
          return;
        }

        setError(true);
      });

    return () => {
      active = false;
    };
  }, [attempt]);

  if (account)
    return (
      <GetStartedWorkflow
        key={account.userId + ":" + account.organizationId}
        account={account}
      />
    );

  if (organizations.length > 1)
    return <OrganizationPicker organizations={organizations} />;

  return (
    <div className="gr-root gs-root">
      <main className="gs-account-gate">
        {error ? (
          <>
            <h1>We couldn’t load your account.</h1>
            <button
              type="button"
              className="gr-button gr-button--main"
              onClick={() => setAttempt((current) => current + 1)}
            >
              Try again
            </button>
            <a className="gs-text-button" href={ENGINEER_SIGNUP_URL}>
              Sign in or create an account <ArrowRight size={14} />
            </a>
          </>
        ) : (
          <>
            <h1>Set up your engineer.</h1>
            <p role="status">Loading your account…</p>
          </>
        )}
        <OnboardingHelp step="Account setup" />
      </main>
    </div>
  );
};
