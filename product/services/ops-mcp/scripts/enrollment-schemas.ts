import { writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { format } from "prettier";
import { z } from "zod";

import {
  enrollmentPayloadSchema,
  enrollmentResultSchema,
} from "../src/instances/enrollment.js";

// The GPU base image validates enrollment against these files.
export const enrollmentSchemaFiles = {
  payload: enrollmentPayloadSchema,
  result: enrollmentResultSchema,
};

export const schemaPath = (name: string) =>
  new URL(
    `../../../inference/host/gradiated_host/enrollment-${name}.schema.json`,
    import.meta.url,
  );

export const renderSchema = (schema: z.ZodType) =>
  format(JSON.stringify(z.toJSONSchema(schema)), { parser: "json" });

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  for (const [name, schema] of Object.entries(enrollmentSchemaFiles))
    await writeFile(schemaPath(name), await renderSchema(schema));
}
