import {
  createAnalytics,
  groupSchemas,
  type GroupProperties,
  type AnalyticsGroup,
} from "@gradiated/analytics";
import { posthog, posthogKey } from "./posthog";

export const analytics = createAnalytics("console", (event, properties) => {
  if (posthogKey) posthog.capture(event, properties);
});

let scopeKey = "";

export const identifyGroup = <Group extends AnalyticsGroup>(
  type: Group,
  id: string,
  properties: GroupProperties<Group>,
) => {
  if (!posthogKey) return;

  const parsed = groupSchemas[type].safeParse(properties);
  if (parsed.success) posthog.group(type, id, parsed.data);
};

export const setAnalyticsScope = (
  userId: string,
  organizationId: string,
  workspaceId: string,
  isDefault: boolean,
) => {
  const nextKey = JSON.stringify([
    userId,
    organizationId,
    workspaceId,
    isDefault,
  ]);
  if (!posthogKey || scopeKey === nextKey) return;

  scopeKey = nextKey;
  posthog.resetGroups();
  identifyGroup("organization", organizationId, {});
  identifyGroup("workspace", workspaceId, {
    organization_id: organizationId,
    is_default: isDefault,
  });
};

export const clearAnalyticsScope = () => {
  scopeKey = "";
};
