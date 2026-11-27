import { randomUUID } from "node:crypto";

import type { OrganizationRole } from "@gradiated/control";
import { jwt } from "better-auth/plugins";

export const TRAINING_TOKEN_AUDIENCE = "training";
export const TRAINING_TOKEN_LIFETIME_SECONDS = 10 * 60;
// grad's internal listener refuses service tokens that live longer than ten minutes.
export const SERVICE_TOKEN_LIFETIME_SECONDS = 5 * 60;

export const SERVICE_TOKEN_SCOPES = [
  "artifacts:pin",
  "workspaces:admin",
] as const;

// The plugin's session token endpoint signs a token without a workspace.
export const DISABLED_JWT_PATHS = ["/token"];

export interface TrainingTokenSubject {
  userId: string;
  organizationId: string;
  workspaceId: string;
  role: OrganizationRole;
}

export interface ServiceTokenSubject {
  // The calling product component, such as inference.
  service: string;
  workspaceId: string;
  scopes: readonly (typeof SERVICE_TOKEN_SCOPES)[number][];
}

export interface TrainingToken {
  token: string;
  expiresAt: Date;
}

export type SignJwt = (input: {
  body: { payload: Record<string, unknown> };
}) => Promise<{ token: string }>;

export const trainingJwt = (issuer: string) =>
  jwt({
    jwks: {
      keyPairConfig: { alg: "ES256" },
      rotationInterval: 90 * 24 * 60 * 60,
    },
    jwt: {
      issuer,
      audience: TRAINING_TOKEN_AUDIENCE,
      expirationTime: `${TRAINING_TOKEN_LIFETIME_SECONDS}s`,
    },
    disableSettingJwtHeader: true,
  });

export const signTrainingToken = async (
  sign: SignJwt,
  subject: TrainingTokenSubject,
  now = new Date(),
): Promise<TrainingToken> => {
  const iat = Math.floor(now.getTime() / 1000);
  const exp = iat + TRAINING_TOKEN_LIFETIME_SECONDS;

  const { token } = await sign({
    body: {
      payload: {
        sub: `user:${subject.userId}`,
        org: subject.organizationId,
        ws: subject.workspaceId,
        role: subject.role,
        jti: randomUUID(),
        iat,
        exp,
      },
    },
  });

  return { token, expiresAt: new Date(exp * 1000) };
};

export const signServiceToken = async (
  sign: SignJwt,
  subject: ServiceTokenSubject,
  now = new Date(),
): Promise<TrainingToken> => {
  if (!/^[a-z][a-z0-9-]{0,62}$/.test(subject.service))
    throw new Error(`Invalid service name: ${subject.service}`);
  if (subject.scopes.length === 0)
    throw new Error("A service token needs at least one scope.");

  const iat = Math.floor(now.getTime() / 1000);
  const exp = iat + SERVICE_TOKEN_LIFETIME_SECONDS;

  const { token } = await sign({
    body: {
      payload: {
        sub: `service:${subject.service}`,
        ws: subject.workspaceId,
        scopes: [...subject.scopes],
        jti: randomUUID(),
        iat,
        exp,
      },
    },
  });

  return { token, expiresAt: new Date(exp * 1000) };
};
