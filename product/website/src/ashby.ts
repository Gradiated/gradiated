// Everything the website knows about Ashby, shared by the API routes in api/,
// the job sync in scripts/sync-ashby-jobs.ts and the form in ApplyForm.tsx.
//
// No imports, so it runs as-is in the browser, in Vercel functions and under
// Node's built-in type stripping.

/** One question on a job's application form, as the browser renders it. */
export type AshbyFormField = {
  path: string;
  title: string;
  type: string;
  required: boolean;
  description: string;
  options: { label: string; value: string }[];
};

/** A posting on the public job board. Only the fields the sync uses. */
export type AshbyPosting = {
  id: string;
  title: string;
  team?: string;
  location?: string;
  secondaryLocations?: { location: string }[];
  publishedAt?: string;
  descriptionHtml?: string;
  isListed?: boolean;
  /** FullTime, PartTime, Intern, Contract or Temporary. */
  employmentType?: string;
};

export type AshbySubmitResult = {
  blocked: boolean;
  blockMessageForCandidateHtml?: string;
};

// How ApplyForm encodes answers in the multipart body it sends to /api/apply:
//   <ashby field path>     one part per answer, e.g. _systemfield_name
//   <path>[]               multi-select answers
//   <path>::boolean        Yes/No answers ("true"/"false"), sent to Ashby as booleans
//   <path>::number         Number answers, sent to Ashby as numbers
//   utm_*                  passed on to Ashby as source data
export const UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
];
export const MULTI_SUFFIX = "[]";
export const BOOLEAN_SUFFIX = "::boolean";
export const NUMBER_SUFFIX = "::number";
/** Vercel caps request bodies at ~4.5MB, so the form limits all files together to 4MB. */
export const MAX_FILE_BYTES = 4 * 1024 * 1024;

/** A failed Ashby call. Carries status and error codes, never the request body. */
export class AshbyError extends Error {
  readonly status: number;
  readonly errors: unknown;

  constructor(endpoint: string, status: number, errors: unknown) {
    super(`Ashby ${endpoint} failed (${status})`);
    this.status = status;
    this.errors = errors;
  }
}

type AshbyFormEntry = {
  isRequired?: boolean;
  descriptionPlain?: string;
  field?: {
    path: string;
    title: string;
    type: string;
    selectableValues?: { label: string; value: string }[];
  };
};

export class AshbyService {
  static readonly API = "https://api.ashbyhq.com";

  readonly #apiKey: string;

  /** The key needs jobsRead + candidatesWrite. The public job board needs none. */
  constructor(apiKey = "") {
    this.#apiKey = apiKey;
  }

  /** Every posting listed on a public job board. */
  async listedPostings(board: string): Promise<AshbyPosting[]> {
    const res = await fetch(
      `${AshbyService.API}/posting-api/job-board/${board}`,
    );
    if (!res.ok) throw new AshbyError("job-board", res.status, null);
    const { jobs = [] }: { jobs?: AshbyPosting[] } = await res.json();
    return jobs.filter((posting) => posting.isListed !== false);
  }

  /** The questions on a job posting's application form. */
  async formFields(jobPostingId: string): Promise<AshbyFormField[]> {
    const results = await this.#call(
      "jobPosting.info",
      JSON.stringify({ jobPostingId }),
    );
    const sections: { fields?: AshbyFormEntry[] }[] =
      results?.applicationFormDefinition?.sections ?? [];

    return sections.flatMap((section) =>
      (section.fields ?? []).map(({ field, isRequired, descriptionPlain }) => ({
        path: field?.path as string,
        title: field?.title as string,
        type: field?.type as string,
        required: Boolean(isRequired),
        description: descriptionPlain ?? "",
        options: (field?.selectableValues ?? []).map(({ label, value }) => ({
          label,
          value,
        })),
      })),
    );
  }

  /** Submits answers encoded the way ApplyForm sends them (see the suffixes above). */
  async submitApplication(
    jobPostingId: string,
    answers: FormData,
  ): Promise<AshbySubmitResult> {
    const body = new FormData();
    const fieldSubmissions: { path: string; value: unknown }[] = [];
    const multiSelects = new Map<string, string[]>();
    const utmData: Record<string, string> = {};
    let fileCount = 0;

    for (const [path, value] of answers.entries()) {
      if (path === "jobPostingId") continue;

      if (UTM_KEYS.includes(path)) {
        if (typeof value === "string" && value) utmData[path] ??= value;
      } else if (typeof value !== "string") {
        if (value.size === 0) continue; // optional file left empty
        // Ashby wants the field's value to be the name of the part holding the bytes.
        const part = `file_${++fileCount}`;
        body.append(part, value, value.name);
        fieldSubmissions.push({ path, value: part });
      } else if (path.endsWith(MULTI_SUFFIX)) {
        const realPath = path.slice(0, -MULTI_SUFFIX.length);
        let values = multiSelects.get(realPath);
        if (!values) {
          values = [];
          multiSelects.set(realPath, values);
          fieldSubmissions.push({ path: realPath, value: values });
        }
        values.push(value);
      } else if (path.endsWith(BOOLEAN_SUFFIX)) {
        // Only Yes/No questions are sent as booleans: the form marks them with this suffix.
        fieldSubmissions.push({
          path: path.slice(0, -BOOLEAN_SUFFIX.length),
          value: value === "true",
        });
      } else if (path.endsWith(NUMBER_SUFFIX)) {
        if (value) {
          fieldSubmissions.push({
            path: path.slice(0, -NUMBER_SUFFIX.length),
            value: Number(value),
          });
        }
      } else if (value) {
        fieldSubmissions.push({ path, value });
      }
    }

    body.append("jobPostingId", jobPostingId);
    // Ashby accepts applications to closed postings unless told otherwise.
    body.append("allowSubmissionForUnpublishedJobPosting", "false");
    body.append("applicationForm", JSON.stringify({ fieldSubmissions }));
    if (Object.keys(utmData).length > 0)
      body.append("utmData", JSON.stringify(utmData));

    const results = await this.#call("applicationForm.submit", body);
    const { blocked, blockMessageForCandidateHtml } =
      results?.formMessages ?? {};
    return { blocked: Boolean(blocked), blockMessageForCandidateHtml };
  }

  /** POSTs to an authenticated endpoint and returns its `results`. */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  async #call(endpoint: string, body: string | FormData): Promise<any> {
    if (!this.#apiKey) throw new Error("ASHBY_API_KEY is not set");
    const headers: Record<string, string> = {
      Accept: "application/json",
      Authorization: `Basic ${btoa(`${this.#apiKey}:`)}`,
    };
    // For FormData, fetch sets the multipart content type and boundary itself.
    if (typeof body === "string") headers["Content-Type"] = "application/json";

    const res = await fetch(`${AshbyService.API}/${endpoint}`, {
      method: "POST",
      headers,
      body,
    });
    const data = await res.json().catch(() => null);
    if (!res.ok || !data?.success) {
      throw new AshbyError(
        endpoint,
        res.status,
        data?.errors ?? data?.errorInfo,
      );
    }
    return data.results;
  }
}
