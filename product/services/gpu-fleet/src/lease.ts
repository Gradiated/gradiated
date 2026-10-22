import { isConflict, type Kubernetes } from "./kubernetes.js";

type Lease = {
  metadata: { name: string; namespace: string; resourceVersion?: string };
  spec: {
    holderIdentity?: string;
    leaseDurationSeconds?: number;
    acquireTime?: string;
    renewTime?: string;
    leaseTransitions?: number;
  };
};

// Kubernetes MicroTime: RFC 3339 with six fractional digits.
const microTime = (date: Date) => date.toISOString().replace("Z", "000Z");

export const createLease = ({
  api,
  namespace,
  name,
  identity,
  durationSeconds,
  now = () => new Date(),
}: {
  api: Kubernetes;
  namespace: string;
  name: string;
  identity: string;
  durationSeconds: number;
  now?: () => Date;
}) => {
  const path = `/apis/coordination.k8s.io/v1/namespaces/${namespace}/leases`;

  const acquire = async () => {
    const time = now();
    const current = (await api.get(`${path}/${name}`)) as Lease | undefined;
    if (!current) {
      try {
        await api.create(path, {
          apiVersion: "coordination.k8s.io/v1",
          kind: "Lease",
          metadata: { name, namespace },
          spec: {
            holderIdentity: identity,
            leaseDurationSeconds: durationSeconds,
            acquireTime: microTime(time),
            renewTime: microTime(time),
            leaseTransitions: 0,
          },
        });
        return true;
      } catch (error) {
        if (isConflict(error)) return false;
        throw error;
      }
    }

    const holder = current.spec.holderIdentity ?? "";
    const renewed = Date.parse(current.spec.renewTime ?? "");
    const duration =
      (current.spec.leaseDurationSeconds ?? durationSeconds) * 1000;
    const expired = !holder || !(renewed + duration > time.getTime());
    if (holder !== identity && !expired) return false;

    const transition = holder !== identity;
    try {
      await api.replace(`${path}/${name}`, {
        ...current,
        spec: {
          ...current.spec,
          holderIdentity: identity,
          leaseDurationSeconds: durationSeconds,
          renewTime: microTime(time),
          ...(transition && {
            acquireTime: microTime(time),
            leaseTransitions: (current.spec.leaseTransitions ?? 0) + 1,
          }),
        },
      });
      return true;
    } catch (error) {
      if (isConflict(error)) return false;
      throw error;
    }
  };

  const release = async () => {
    const current = (await api.get(`${path}/${name}`)) as Lease | undefined;
    if (current?.spec.holderIdentity !== identity) return;
    await api
      .replace(`${path}/${name}`, {
        ...current,
        spec: { ...current.spec, holderIdentity: "" },
      })
      .catch((error: unknown) => {
        if (!isConflict(error)) throw error;
      });
  };

  return { acquire, release };
};
