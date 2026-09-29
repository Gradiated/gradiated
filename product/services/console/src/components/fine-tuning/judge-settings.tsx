import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateWorkspace } from "@/api/queries";
import { useProductContext } from "@/hooks/use-product-context";
import { queryKeys } from "@/lib/query-keys";
import {
  EVALUATION_JUDGE_ALLOWLIST,
  type EvaluationJudge,
} from "@/store/fine-tuning-types";
import { SettingRow } from "./settings-card";

export const JudgeSettings = () => {
  const { organizationId, workspaceId, workspaces, selectedOrganization } =
    useProductContext();
  const workspace = workspaces.find((row) => row.id === workspaceId);
  const client = useQueryClient();
  const save = useMutation({
    mutationFn: (evaluation_judge: EvaluationJudge) =>
      updateWorkspace(organizationId, workspaceId, { evaluation_judge }),
    onSuccess: () =>
      client.invalidateQueries({
        queryKey: queryKeys.workspaces(organizationId),
      }),
  });
  const canEdit =
    selectedOrganization?.status === "active" &&
    ["owner", "admin"].includes(selectedOrganization.role);

  if (!workspace) return null;

  return (
    <>
      <SettingRow
        title="Judge model"
        description="This is the model used to compare fine-tuned models vs existing models to decide which is better."
      >
        <select
          aria-label="Judge model"
          className="w-64 rounded-md border bg-background p-2 font-mono text-xs"
          value={workspace.evaluation_judge}
          disabled={!canEdit || save.isPending}
          onChange={(event) =>
            save.mutate(event.target.value as EvaluationJudge)
          }
        >
          {EVALUATION_JUDGE_ALLOWLIST.map((judge) => (
            <option key={judge} value={judge}>
              {judge}
            </option>
          ))}
        </select>
      </SettingRow>
      {save.error ? (
        <p role="alert" className="p-4 text-sm text-destructive">
          {save.error.message}
        </p>
      ) : null}
    </>
  );
};
