import { z } from "@hono/zod-openapi";

export const ProblemSchema = z
  .object({
    type: z
      .string()
      .url()
      .openapi({ example: "https://gradiated.com/problems/validation" }),
    title: z.string().min(1).max(200),
    status: z.number().int().min(400).max(599),
    detail: z.string().min(1).max(2_000),
    code: z.string().regex(/^[a-z][a-z0-9_]*$/),
    request_id: z.string().min(1),
    errors: z
      .array(
        z.object({
          path: z.string().max(500),
          message: z.string().max(500),
        }),
      )
      .max(100)
      .optional(),
  })
  .openapi("Problem");

export type Problem = z.infer<typeof ProblemSchema>;

export const problemContent = {
  "application/problem+json": {
    schema: ProblemSchema,
  },
} as const;
