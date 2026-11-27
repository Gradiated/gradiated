import { z } from "zod";
import { PODS } from "./hosts.js";

export const POD_NAMESPACE = PODS.split("/")[4]!;

const requirement = z.object({
  key: z.string(),
  operator: z.enum(["In", "NotIn", "Exists", "DoesNotExist", "Gt", "Lt"]),
  values: z.array(z.string()).nullish(),
});

const antiAffinityTerm = z.object({
  topologyKey: z.string(),
  namespaces: z.array(z.string()).nullish(),
  namespaceSelector: z.record(z.string(), z.unknown()).nullish(),
  labelSelector: z
    .object({
      matchLabels: z.record(z.string(), z.string()).nullish(),
      matchExpressions: z.array(requirement).nullish(),
    })
    .nullish(),
  matchLabelKeys: z.array(z.string()).nullish(),
  mismatchLabelKeys: z.array(z.string()).nullish(),
});

export const podPlacementSchema = z.object({
  nodeSelector: z.record(z.string(), z.string()).nullish(),
  tolerations: z
    .array(
      z.object({
        key: z.string().optional(),
        operator: z.enum(["Equal", "Exists"]).optional(),
        value: z.string().optional(),
        effect: z
          .enum(["NoSchedule", "NoExecute", "PreferNoSchedule"])
          .optional(),
      }),
    )
    .nullish(),
  affinity: z
    .object({
      nodeAffinity: z
        .object({
          requiredDuringSchedulingIgnoredDuringExecution: z
            .object({
              nodeSelectorTerms: z.array(
                z.object({
                  matchExpressions: z.array(requirement).nullish(),
                  matchFields: z.array(requirement).nullish(),
                }),
              ),
            })
            .nullish(),
        })
        .nullish(),
      podAffinity: z
        .object({
          requiredDuringSchedulingIgnoredDuringExecution: z
            .array(z.unknown())
            .nullish(),
        })
        .nullish(),
      podAntiAffinity: z
        .object({
          requiredDuringSchedulingIgnoredDuringExecution: z
            .array(antiAffinityTerm)
            .nullish(),
        })
        .nullish(),
    })
    .nullish(),
});

export type PodPlacement = z.infer<typeof podPlacementSchema>;
export type NodePlacement = {
  name?: string;
  labels?: Record<string, string>;
  taints?: { key: string; value?: string; effect: string }[];
};

export type PlacedPod = {
  labels?: Record<string, string>;
  namespace?: string;
  placement?: PodPlacement;
  node: NodePlacement;
};

type PlacementContext = {
  labels: Record<string, string>;
  namespace: string;
  residents: PlacedPod[];
};

const satisfies = (
  rule: z.infer<typeof requirement>,
  labels: Record<string, string>,
) => {
  const value = labels[rule.key];
  const values = rule.values ?? [];
  switch (rule.operator) {
    case "In":
      return value !== undefined && values.includes(value);
    case "NotIn":
      return value === undefined || !values.includes(value);
    case "Exists":
      return value !== undefined;
    case "DoesNotExist":
      return value === undefined;
    case "Gt":
    case "Lt":
      return (
        value !== undefined &&
        /^-?\d+$/.test(value) &&
        values.length === 1 &&
        /^-?\d+$/.test(values[0]!) &&
        (rule.operator === "Gt"
          ? Number(value) > Number(values[0])
          : Number(value) < Number(values[0]))
      );
  }
};

const antiAffinityFits = (
  owner: Omit<PlacementContext, "residents">,
  placement: PodPlacement | undefined,
  node: NodePlacement,
  others: PlacedPod[],
) =>
  (
    placement?.affinity?.podAntiAffinity
      ?.requiredDuringSchedulingIgnoredDuringExecution ?? []
  ).every((term) => {
    // The fleet reads its pod namespace, not namespace labels or other namespaces.
    if (
      term.topologyKey !== "kubernetes.io/hostname" ||
      term.namespaceSelector != null ||
      term.matchLabelKeys?.length ||
      term.mismatchLabelKeys?.length
    )
      return false;

    const namespaces = term.namespaces?.length
      ? term.namespaces
      : [owner.namespace];
    if (namespaces.some((namespace) => namespace !== owner.namespace))
      return false;
    if (!term.labelSelector) return true;

    const topology = node.labels?.[term.topologyKey];
    if (topology === undefined) return false;

    return others.every((other) => {
      if ((other.namespace ?? POD_NAMESPACE) !== owner.namespace) return true;
      const labels = other.labels ?? {};
      const selects =
        Object.entries(term.labelSelector?.matchLabels ?? {}).every(
          ([key, value]) => labels[key] === value,
        ) &&
        (term.labelSelector?.matchExpressions ?? []).every((rule) =>
          satisfies(rule, labels),
        );
      return (
        !selects ||
        (other.node.labels?.[term.topologyKey] !== undefined &&
          other.node.labels[term.topologyKey] !== topology)
      );
    });
  });

export const placementFits = (
  pod: PodPlacement | undefined,
  node: NodePlacement,
  context?: PlacementContext,
) => {
  const labels = node.labels ?? {};
  if (
    Object.entries(pod?.nodeSelector ?? {}).some(
      ([key, value]) => labels[key] !== value,
    )
  )
    return false;

  const affinity = pod?.affinity;
  if (
    affinity?.podAffinity?.requiredDuringSchedulingIgnoredDuringExecution
      ?.length
  )
    return false;

  const antiAffinity =
    affinity?.podAntiAffinity?.requiredDuringSchedulingIgnoredDuringExecution;
  if (antiAffinity?.length && !context) return false;
  if (
    context &&
    (!antiAffinityFits(context, pod, node, context.residents) ||
      !context.residents.every((resident) =>
        antiAffinityFits(
          {
            labels: resident.labels ?? {},
            namespace: resident.namespace ?? POD_NAMESPACE,
          },
          resident.placement,
          resident.node,
          [
            {
              labels: context.labels,
              namespace: context.namespace,
              placement: pod ?? {},
              node,
            },
          ],
        ),
      ))
  )
    return false;

  const required =
    affinity?.nodeAffinity?.requiredDuringSchedulingIgnoredDuringExecution;
  if (
    required &&
    !required.nodeSelectorTerms.some((term) => {
      const expressions = term.matchExpressions ?? [];
      const fields = term.matchFields ?? [];
      return (
        expressions.length + fields.length > 0 &&
        expressions.every((rule) => satisfies(rule, labels)) &&
        fields.every(
          (rule) =>
            rule.key === "metadata.name" &&
            node.name !== undefined &&
            satisfies(rule, { "metadata.name": node.name }),
        )
      );
    })
  )
    return false;

  return (node.taints ?? []).every(
    (taint) =>
      taint.effect === "PreferNoSchedule" ||
      (pod?.tolerations ?? []).some(
        (toleration) =>
          (!toleration.effect || toleration.effect === taint.effect) &&
          ((toleration.operator ?? "Equal") === "Exists"
            ? !toleration.key || toleration.key === taint.key
            : toleration.key === taint.key &&
              (toleration.value ?? "") === (taint.value ?? "")),
      ),
  );
};
