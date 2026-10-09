# Analytics

Shared product event schemas, TypeScript property types, source ownership, and
PostHog group attribution. See the [event catalogue](../../../docs/PRODUCT_ANALYTICS.md).

```ts
import { createAnalytics } from "@gradiated/analytics";

const analytics = createAnalytics("console", (event, properties) => {
  posthog.capture(event, properties);
});
analytics.track("workspace_selected", {
  organization_id: organization.id,
  workspace_id: workspace.id,
});
```

`track` returns whether validation and the transport callback succeeded, not
whether PostHog ingested the event. Invalid properties and source mismatches
return false. It never forwards unknown properties.

The `@gradiated/analytics/server` export provides a bounded, non-blocking HTTP
capture transport with retry and shutdown draining. The API integration resolves
resource ownership, attaches actor identity, and supplies group metadata. The
console uses its existing PostHog SDK/feature-flag initialization and corrects
persisted group merging at the final SDK send boundary.
