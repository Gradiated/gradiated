import { useSearchParams } from "react-router-dom";
import { AccountOnboarding } from "../components/get-started/AccountOnboarding";
import { OnboardingHelp } from "../components/get-started/OnboardingParts";
import "../styles/index.css";
import "../styles/onboarding.css";

export const GetStartedPage = () => {
  const [search] = useSearchParams();
  if (search.get("github_authorized") === "1")
    return (
      <div className="gr-root gs-root">
        <main className="gs-account-gate">
          <h1>Return to setup</h1>
          <p>
            Return to the original tab to check your GitHub installation. You
            can close this tab.
          </p>
          <OnboardingHelp step="GitHub authorization" />
        </main>
      </div>
    );

  return <AccountOnboarding key={search.get("organization") ?? "default"} />;
};
