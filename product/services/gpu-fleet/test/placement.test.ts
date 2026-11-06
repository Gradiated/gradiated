import { describe, expect, it } from "vitest";

import { placementFits, podPlacementSchema } from "../src/placement.js";

describe("relocation placement", () => {
  const reserved = {
    key: "gradiated.com/kimi-k31",
    value: "reserved",
    effect: "NoSchedule",
  };

  it("requires matching toleration key, value and effect for reservation taints", () => {
    const node = { taints: [reserved] };
    expect(placementFits({}, node)).toBe(false);
    for (const toleration of [
      reserved,
      { key: reserved.key, operator: "Exists" as const },
    ])
      expect(
        placementFits(
          podPlacementSchema.parse({ tolerations: [toleration] }),
          node,
        ),
      ).toBe(true);
    for (const toleration of [
      { ...reserved, value: "other" },
      { ...reserved, effect: "NoExecute" },
    ])
      expect(
        placementFits(
          podPlacementSchema.parse({ tolerations: [toleration] }),
          node,
        ),
      ).toBe(false);
    expect(
      placementFits(
        {},
        { taints: [{ ...reserved, effect: "PreferNoSchedule" }] },
      ),
    ).toBe(true);
  });

  it("keeps required selectors and affinity while ignoring preferred affinity", () => {
    const pod = podPlacementSchema.parse({
      nodeSelector: { product: "B300" },
      affinity: {
        nodeAffinity: {
          requiredDuringSchedulingIgnoredDuringExecution: {
            nodeSelectorTerms: [
              {
                matchExpressions: [
                  { key: "instance", operator: "In", values: ["second"] },
                ],
              },
              {
                matchFields: [
                  {
                    key: "metadata.name",
                    operator: "In",
                    values: ["gpu-third"],
                  },
                ],
              },
            ],
          },
        },
      },
    });
    expect(
      placementFits(pod, { labels: { product: "B300", instance: "first" } }),
    ).toBe(false);
    expect(
      placementFits(pod, { labels: { product: "B300", instance: "second" } }),
    ).toBe(true);
    expect(
      placementFits(pod, { name: "gpu-third", labels: { product: "B300" } }),
    ).toBe(true);
    expect(
      placementFits(pod, { name: "gpu-third", labels: { product: "H200" } }),
    ).toBe(false);
  });

  it("fails closed for empty required terms and required inter-pod affinity", () => {
    for (const nodeSelectorTerms of [[], [{}]]) {
      const pod = podPlacementSchema.parse({
        affinity: {
          nodeAffinity: {
            requiredDuringSchedulingIgnoredDuringExecution: {
              nodeSelectorTerms,
            },
          },
        },
      });
      expect(placementFits(pod, {})).toBe(false);
    }
    expect(
      placementFits(
        podPlacementSchema.parse({
          affinity: {
            podAntiAffinity: {
              requiredDuringSchedulingIgnoredDuringExecution: [
                { topologyKey: "kubernetes.io/hostname" },
              ],
            },
          },
        }),
        {},
      ),
    ).toBe(false);
  });

  it("checks required hostname anti-affinity against actual and planned residents", () => {
    const selector = { matchLabels: { app: "glm" } };
    const placement = podPlacementSchema.parse({
      affinity: {
        podAntiAffinity: {
          requiredDuringSchedulingIgnoredDuringExecution: [
            { topologyKey: "kubernetes.io/hostname", labelSelector: selector },
          ],
        },
      },
    });
    const first = { labels: { "kubernetes.io/hostname": "first" } };
    const second = { labels: { "kubernetes.io/hostname": "second" } };
    const context = {
      namespace: "inference",
      labels: { app: "glm" },
      residents: [
        { labels: { app: "glm" }, namespace: "inference", node: first },
      ],
    };
    expect(placementFits(placement, second, context)).toBe(true);
    expect(placementFits(placement, first, context)).toBe(false);
    expect(
      placementFits(placement, second, {
        ...context,
        residents: [
          ...context.residents,
          { labels: { app: "glm" }, namespace: "inference", node: second },
        ],
      }),
    ).toBe(false);
    expect(
      placementFits(placement, second, {
        ...context,
        residents: [
          { labels: { app: "other" }, namespace: "inference", node: second },
        ],
      }),
    ).toBe(true);
    expect(
      placementFits({}, second, {
        ...context,
        residents: [
          {
            labels: { app: "glm" },
            namespace: "inference",
            placement,
            node: second,
          },
        ],
      }),
    ).toBe(false);
  });
});
