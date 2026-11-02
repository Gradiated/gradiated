export interface SmgAdmission {
  readonly inflight: number;
  readonly queued: number;
}

export interface SmgAdmissionSample {
  readonly inflight: number;
  readonly queued: number | null;
}

const gauge = (metrics: string, name: string): number | null => {
  const values = metrics.split("\n").flatMap((line) => {
    const sample = line.match(
      /^([a-z_:][a-z0-9_:]*)(?:\{.*\})?\s+([-+0-9.eE]+)(?:\s+\d+)?$/i,
    );
    return sample?.[1] === name ? [Number(sample[2])] : [];
  });
  if (values.some((value) => !Number.isSafeInteger(value) || value < 0)) {
    throw new Error(`native SMG gauge invalid: ${name}`);
  }

  return values.length > 0
    ? values.reduce((sum, value) => sum + value, 0)
    : null;
};

export const smgAdmissionSample = (metrics: string): SmgAdmissionSample => {
  const inflight = gauge(metrics, "smg_admission_inflight");
  if (inflight === null)
    throw new Error("native SMG inflight gauge unavailable");

  return {
    inflight,
    queued: gauge(metrics, "smg_admission_queue_depth"),
  };
};

export const smgAdmission = (metrics: string): SmgAdmission => {
  const sample = smgAdmissionSample(metrics);
  if (sample.queued === null)
    throw new Error("native SMG queue gauge unavailable");

  return { inflight: sample.inflight, queued: sample.queued };
};
