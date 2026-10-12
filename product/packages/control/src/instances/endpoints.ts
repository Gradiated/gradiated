import { z } from "zod";

export const privateServingUrl = (instanceId: string): string =>
  `http://gpu-${z.uuid().parse(instanceId).toLowerCase()}.tailscale-inference.svc.cluster.local:8888`;
