import { z } from "zod";

export const settlementSlotIdSchema = z
  .string()
  .regex(/^\d{8}T\d{6}Z-300s-v1$/);

export const settlementSourceId = (
  slotId: string,
  organizationId: string,
): string => `${slotId}:${organizationId}`;
