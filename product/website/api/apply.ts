// POST /api/apply  (multipart/form-data from src/components/ApplyForm.tsx)
//
// Forwards an application to Ashby's applicationForm.submit. Same approach as
// posthog.com's api/apply.js, using built-in fetch/FormData so there are no
// extra dependencies. Env: ASHBY_API_KEY (jobsRead + candidatesWrite).
//
// The browser sends:
//   jobPostingId           the Ashby job posting id
//   <ashby field path>     one part per answer, e.g. _systemfield_name
//   <path>[]               multi-select answers
//   <path>::boolean        Yes/No answers ("true"/"false"), sent to Ashby as booleans
//   utm_*                  passed on to Ashby as source data
//
// Vercel caps request bodies at ~4.5MB, so the form limits files to 4MB.

declare const process: { env: Record<string, string | undefined> };

const auth = (): string => `Basic ${btoa(`${process.env.ASHBY_API_KEY ?? ""}:`)}`;

const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];
const BOOLEAN_SUFFIX = "::boolean";

export async function POST(request: Request): Promise<Response> {
  let incoming: FormData;
  try {
    incoming = await request.formData();
  } catch {
    return Response.json({ success: false, error: "Bad form data" }, { status: 400 });
  }

  const jobPostingId = incoming.get("jobPostingId");
  if (typeof jobPostingId !== "string" || !jobPostingId) {
    return Response.json({ success: false, error: "Missing jobPostingId" }, { status: 400 });
  }

  const outgoing = new FormData();
  const fieldSubmissions: { path: string; value: unknown }[] = [];
  let fileCount = 0;

  for (const [path, value] of incoming.entries()) {
    if (path === "jobPostingId" || UTM_KEYS.includes(path)) continue;

    if (typeof value !== "string") {
      if (value.size === 0) continue; // optional file left empty
      // Ashby wants the field's value to be the name of the part holding the bytes.
      const key = `file_${++fileCount}`;
      outgoing.append(key, value, value.name);
      fieldSubmissions.push({ path, value: key });
    } else if (path.endsWith("[]")) {
      const realPath = path.slice(0, -2);
      const existing = fieldSubmissions.find((field) => field.path === realPath);
      if (existing) (existing.value as string[]).push(value);
      else fieldSubmissions.push({ path: realPath, value: [value] });
    } else if (path.endsWith(BOOLEAN_SUFFIX)) {
      // Only Yes/No questions are sent as booleans: the form marks them with this suffix.
      fieldSubmissions.push({ path: path.slice(0, -BOOLEAN_SUFFIX.length), value: value === "true" });
    } else if (value !== "") {
      fieldSubmissions.push({ path, value });
    }
  }

  const utmData: Record<string, string> = {};
  for (const key of UTM_KEYS) {
    const value = incoming.get(key);
    if (typeof value === "string" && value) utmData[key] = value;
  }

  outgoing.append("jobPostingId", jobPostingId);
  outgoing.append("applicationForm", JSON.stringify({ fieldSubmissions }));
  if (Object.keys(utmData).length > 0) outgoing.append("utmData", JSON.stringify(utmData));

  const res = await fetch("https://api.ashbyhq.com/applicationForm.submit", {
    method: "POST",
    headers: { Accept: "application/json", Authorization: auth() },
    body: outgoing, // fetch sets the multipart boundary
  });

  const data = await res.json().catch(() => null);

  if (!res.ok || !data?.success) {
    // Status and error codes only, never the candidate's answers.
    console.error("Ashby applicationForm.submit failed", res.status, data?.errors ?? data?.errorInfo);
    return Response.json(
      { success: false, error: "Failed to submit application" },
      { status: res.ok ? 422 : 502 },
    );
  }

  const { blocked, blockMessageForCandidateHtml } = data.results?.formMessages ?? {};
  return Response.json({ success: true, blocked: Boolean(blocked), blockMessageForCandidateHtml });
}
