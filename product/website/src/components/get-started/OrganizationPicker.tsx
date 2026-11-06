import { useSearchParams } from "react-router-dom";
import type { CurrentUser } from "../../api/queries";
import { Field, OnboardingHelp, StepTitle } from "./OnboardingParts";

export const OrganizationPicker = ({
  organizations,
}: {
  organizations: CurrentUser["organizations"];
}) => {
  const [search, setSearch] = useSearchParams();

  return (
    <div className="gr-root gs-root">
      <div className="gs-auth-shell">
        <main className="gs-main gs-auth-container">
          <StepTitle title="Choose your organization.">
            Which team is this engineer for?
          </StepTitle>
          <Field label="Organization">
            <select
              defaultValue=""
              onChange={(event) => {
                const next = new URLSearchParams(search);
                next.set("organization", event.target.value);
                setSearch(next);
              }}
            >
              <option value="" disabled>
                Choose an organization
              </option>
              {organizations.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </select>
          </Field>
          <OnboardingHelp step="Choose an organization" />
        </main>
      </div>
    </div>
  );
};
