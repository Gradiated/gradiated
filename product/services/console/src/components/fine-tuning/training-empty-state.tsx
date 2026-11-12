import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";

import { getEngineerOnboarding } from "@/api/engineer-onboarding";
import { Button } from "@/components/ui/button";
import { useProductContext } from "@/hooks/use-product-context";
import {
  engineerOnboardingKey,
  type OnboardingSearch,
} from "@/lib/engineer-onboarding";
import { POST_TRAINING_JOURNEY } from "@/lib/login-search";

/* Shown on Training before any task exists. It sends the organization to
   post-training onboarding, or, once that is submitted, says a researcher has
   it. Connecting a task by hand stays available as the secondary action. */
export const TrainingEmptyState = ({
  onConnect,
}: {
  onConnect: () => void;
}) => {
  const { organizationId } = useProductContext();
  const onboarding = useQuery({
    queryKey: engineerOnboardingKey(organizationId),
    queryFn: () => getEngineerOnboarding(organizationId),
    enabled: organizationId !== "",
    retry: false,
  });
  const started = Boolean(onboarding.data?.submitted_at);
  const search: OnboardingSearch = {
    journey: POST_TRAINING_JOURNEY,
    ...(organizationId ? { organization: organizationId } : {}),
  };

  return (
    <div className="flex flex-col gap-5 rounded-xl border bg-card p-6 shadow-sm">
      <div className="flex max-w-xl flex-col gap-1.5">
        <h3 className="text-base font-semibold">
          {started
            ? "Your post-training project has started"
            : "Train your first model with a post-training researcher"}
        </h3>
        <p className="text-sm leading-6 text-muted-foreground">
          {started
            ? "One of our researchers will pick it up from here. Your first trained model shows up on this page."
            : "Connect your code and tell us where to reach you. A post-training researcher picks a first test case with you and trains a model for it."}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        {started ? (
          <Button asChild variant="outline">
            <Link to="/onboarding" search={search}>
              View project
            </Link>
          </Button>
        ) : (
          <Button asChild>
            <Link to="/onboarding" search={search}>
              Start project
              <ArrowRight />
            </Link>
          </Button>
        )}
        <button
          type="button"
          className="text-sm text-muted-foreground underline underline-offset-4"
          onClick={onConnect}
        >
          Or connect a task yourself
        </button>
      </div>
    </div>
  );
};
