// GET /api/ashby-form?jobPostingId=<uuid>
//
// Returns the Ashby application form for a job posting, so the job page shows
// whatever questions are set up on that job in Ashby. The API key never leaves
// the server. Env: ASHBY_API_KEY (jobsRead + candidatesWrite).

declare const process: { env: Record<string, string | undefined> };

const auth = (): string => `Basic ${btoa(`${process.env.ASHBY_API_KEY ?? ""}:`)}`;

export async function GET(request: Request): Promise<Response> {
  const jobPostingId = new URL(request.url).searchParams.get("jobPostingId");
  if (!jobPostingId) {
    return Response.json({ error: "Missing jobPostingId" }, { status: 400 });
  }

  const res = await fetch("https://api.ashbyhq.com/jobPosting.info", {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: auth(),
    },
    body: JSON.stringify({ jobPostingId }),
  });

  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success) {
    console.error("Ashby jobPosting.info failed", res.status, data?.errors);
    return Response.json({ error: "Could not load application form" }, { status: 502 });
  }

  const sections = data.results?.applicationFormDefinition?.sections ?? [];
  const fields = sections.flatMap((section: any) =>
    (section.fields ?? []).map((entry: any) => ({
      path: entry.field?.path,
      title: entry.field?.title,
      type: entry.field?.type,
      required: Boolean(entry.isRequired),
      description: entry.descriptionPlain ?? "",
      options: (entry.field?.selectableValues ?? []).map((option: any) => ({
        label: option.label,
        value: option.value,
      })),
    })),
  );

  return Response.json(
    { fields },
    // Edge-cached for 5 minutes, so form edits in Ashby show up quickly.
    { headers: { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600" } },
  );
}
