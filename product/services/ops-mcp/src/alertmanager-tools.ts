import { z } from "zod";

import type { Backend } from "./backend.js";
import type { RegisterReadTool } from "./tools.js";

const matchers = z
  .array(z.string().min(1).max(500))
  .max(20)
  .optional()
  .describe(
    'Alertmanager matchers such as alertname="WorkerLoopFailing" or severity=~"critical|warning"; all must match.',
  );

export const registerAlertmanagerTools = (
  register: RegisterReadTool,
  backend: Backend,
) => {
  register(
    "alertmanager_alerts",
    "Alerts as Alertmanager holds them after routing: labels, annotations, startsAt and endsAt, receivers, and status (active, suppressed) with the silences and inhibitions that suppress each one. Use it to learn whether an alert notified anyone or was silenced; active_alerts shows rule state instead.",
    {
      filter: matchers,
      active: z.boolean().optional(),
      silenced: z.boolean().optional(),
      inhibited: z.boolean().optional(),
      receiver: z.string().min(1).max(200).optional(),
    },
    ({ filter, active, silenced, inhibited, receiver }) =>
      backend("alertmanager", "/api/v2/alerts", {
        ...(filter && { filter }),
        ...(active !== undefined && { active: String(active) }),
        ...(silenced !== undefined && { silenced: String(silenced) }),
        ...(inhibited !== undefined && { inhibited: String(inhibited) }),
        ...(receiver && { receiver }),
      }),
  );

  register(
    "alertmanager_silences",
    "Silences with their matchers, state (active, pending, expired), start and end times, author and comment. Check it before concluding that an alert did not fire or that nobody was paged.",
    { filter: matchers },
    ({ filter }) =>
      backend("alertmanager", "/api/v2/silences", {
        ...(filter && { filter }),
      }),
  );
};
