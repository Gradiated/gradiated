import { useSearch } from "@tanstack/react-router";
import { useEffect } from "react";

import { AuthCard } from "@/components/auth-card";
import { StepTitle } from "@/pages/engineer-onboarding/onboarding-steps";

/* GitHub returns here in the tab the setup page opened. The setup page is
   already polling for the installation, so this tab only needs to close. */
export const GithubReturnPage = () => {
  const { error } = useSearch({ from: "/onboarding/github-connected" });

  useEffect(() => {
    if (!error) window.close();
  }, [error]);

  return (
    <AuthCard>
      <div className="flex flex-col gap-2 p-6 md:p-9">
        {error ? (
          <StepTitle title="GitHub didn’t connect">
            Close this tab and choose Install GitHub app again on the setup
            page.
          </StepTitle>
        ) : (
          <StepTitle title="GitHub is connected">
            You can close this tab and return to your setup.
          </StepTitle>
        )}
      </div>
    </AuthCard>
  );
};
