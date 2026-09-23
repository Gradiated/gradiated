// The service logger emits a code as error_code only when it matches
// /^E[A-Z_]{2,30}$/; it never logs the message.
export type WorkerErrorCode =
  | "EINVALID_STREAM_ID"
  | "EINVALID_SETTLEMENT_SLOT"
  | "EINVALID_STREAM_ENTRY"
  | "EINVALID_GENERATION_JSON"
  | "EINVALID_GENERATION_EVENT"
  | "ECONSUMER_GROUP_MISSING"
  | "ESLOT_MISMATCH"
  | "EDUPLICATE_ORGANIZATION"
  | "ECHARGE_WITHOUT_GENERATIONS"
  | "EMISSING_BILLING_ACCOUNT"
  | "EGENERATION_FINANCIAL_CONFLICT"
  | "ESETTLEMENT_CONFLICT";

export class WorkerInvariantError extends Error {
  override readonly name = "WorkerInvariantError";

  constructor(
    readonly code: WorkerErrorCode,
    message: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
  }
}
