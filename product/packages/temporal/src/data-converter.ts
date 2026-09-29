import { fileURLToPath } from "node:url";
import type { DataConverter } from "@temporalio/common";
import { EncryptionCodec, type PayloadKeys } from "./payload-codec.js";

export const createDataConverter = async (
  payloadKeys: PayloadKeys,
): Promise<DataConverter> => ({
  payloadCodecs: [await EncryptionCodec.create(payloadKeys)],
  failureConverterPath: fileURLToPath(
    new URL("./failure-converter.js", import.meta.url),
  ),
});
