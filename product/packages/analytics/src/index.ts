import { z } from "zod";

const id = z.string().min(1).max(200);
const organization = { organization_id: id };
const workspace = { ...organization, workspace_id: id };
const method = z.enum(["google", "github", "magic_link"]);

export const eventSchemas = {
  user_signed_up: z.strictObject({ ...workspace, user_id: id }),
  user_signed_in: z.strictObject({ user_id: id, session_id: id }),
  sign_out_clicked: z.strictObject({ user_id: id }),
  organization_selected: z.strictObject({ ...organization }),
  workspace_selected: z.strictObject({ ...workspace }),
  api_key_create_clicked: z.strictObject({ ...workspace }),
  api_key_copy_clicked: z.strictObject({ ...workspace, api_key_id: id }),
  billing_top_up_clicked: z.strictObject({ ...organization }),
  workspace_archived: z.strictObject({ ...workspace }),
  sign_in_started: z.strictObject({ method }),
  sign_in_link_sent: z.strictObject({ method: z.literal("magic_link") }),
  organization_created: z.strictObject({
    ...organization,
    default_workspace_id: id,
  }),
  organization_settings_updated: z.strictObject({
    ...organization,
    changed_fields: z
      .array(
        z.enum(["name", "slug", "auto_join_domain", "onboarding_completed"]),
      )
      .min(1),
  }),
  organization_members_invited: z.strictObject({
    ...organization,
    invitation_count: z.number().int().min(1).max(20),
  }),
  organization_invitation_accepted: z.strictObject({ ...organization }),
  organization_member_role_changed: z.strictObject({
    ...organization,
    role: z.enum(["admin", "member"]),
  }),
  organization_member_removed: z.strictObject({ ...organization }),
  workspace_created: z.strictObject({ ...workspace, is_default: z.boolean() }),
  workspace_settings_updated: z.strictObject({
    ...workspace,
    changed_fields: z
      .array(
        z.enum([
          "name",
          "default_judge_model",
          "trace_capture_enabled",
          "trace_retention_days",
        ]),
      )
      .min(1),
  }),
  api_key_created: z.strictObject({
    ...workspace,
    api_key_id: id,
    has_expiry: z.boolean(),
  }),
  api_key_revoked: z.strictObject({ ...workspace, api_key_id: id }),
  billing_checkout_started: z.strictObject({
    ...organization,
    amount_nano_usd: z.string().regex(/^[1-9]\d*$/),
    currency: z.literal("USD"),
  }),
  task_settings_updated: z.strictObject({
    ...workspace,
    task_id: id,
    changed_fields: z
      .array(
        z.enum([
          "judge_model_id",
          "training_schedule",
          "base_model_id",
          "comparison_model_id",
        ]),
      )
      .min(1),
  }),
  training_run_requested: z.strictObject({
    ...workspace,
    task_id: id,
    run_id: id,
  }),
  training_run_cancellation_requested: z.strictObject({
    ...workspace,
    run_id: id,
  }),
  task_version_promoted: z.strictObject({
    ...workspace,
    task_id: id,
    version_id: id,
  }),
  task_version_published: z.strictObject({
    ...workspace,
    task_id: id,
    version_id: id,
  }),
} as const;

export type AnalyticsEvent = keyof typeof eventSchemas;
export type EventProperties<Event extends AnalyticsEvent> = z.infer<
  (typeof eventSchemas)[Event]
>;
export type AnalyticsSource = "console" | "api";
const consoleEvents = new Set<AnalyticsEvent>([
  "sign_out_clicked",
  "sign_in_started",
  "sign_in_link_sent",
  "organization_selected",
  "workspace_selected",
  "api_key_create_clicked",
  "api_key_copy_clicked",
  "billing_top_up_clicked",
]);
export const groupSchemas = {
  organization: z.strictObject({
    status: z.enum(["active", "suspended"]).optional(),
  }),
  workspace: z.strictObject({ organization_id: id, is_default: z.boolean() }),
};
export type AnalyticsGroup = keyof typeof groupSchemas;
export type GroupProperties<Group extends AnalyticsGroup> = z.infer<
  (typeof groupSchemas)[Group]
>;
export type AnalyticsGroups = { organization?: string; workspace?: string };
export type WorkspaceEvent = {
  [Event in AnalyticsEvent]: EventProperties<Event> extends {
    workspace_id: string;
    organization_id: string;
  }
    ? Event
    : never;
}[AnalyticsEvent];
export const changedFields = <Input extends object>(input: Input) =>
  Object.keys(input) as Array<keyof Input & string>;

export const groupsFor = (properties: {
  organization_id?: string;
  workspace_id?: string;
}): AnalyticsGroups => ({
  ...(properties.organization_id
    ? { organization: properties.organization_id }
    : {}),
  ...(properties.workspace_id ? { workspace: properties.workspace_id } : {}),
});

export const createAnalytics = (
  source: AnalyticsSource,
  capture: (event: AnalyticsEvent, properties: Record<string, unknown>) => void,
) => ({
  track: <Event extends AnalyticsEvent>(
    event: Event,
    properties: EventProperties<Event>,
  ): boolean => {
    if (consoleEvents.has(event) !== (source === "console")) return false;

    const parsed = eventSchemas[event].safeParse(properties);
    if (!parsed.success) return false;

    try {
      capture(event, {
        ...parsed.data,
        schema_version: 1,
        source,
        $groups: groupsFor(
          parsed.data as { organization_id?: string; workspace_id?: string },
        ),
      });
      return true;
    } catch {
      return false;
    }
  },
});
