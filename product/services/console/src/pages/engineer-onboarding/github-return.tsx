import { useSearch } from "@tanstack/react-router";
import { useEffect } from "react";

import { AuthCard } from "@/components/auth-card";
import { githubLinkProblem } from "@/lib/engineer-onboarding";

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
        <h1 className="text-2xl font-bold tracking-tight">
          {error ? "GitHub didn’t connect" : "GitHub is connected"}
        </h1>
        <p className="text-sm leading-6 text-muted-foreground">
          {error
            ? githubLinkProblem(error)
            : "You can close this tab and return to your setup."}
        </p>
      </div>
    </AuthCard>
  );
};
