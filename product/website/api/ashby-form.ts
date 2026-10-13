// GET /api/ashby-form?jobPostingId=<uuid>
//
// Returns the Ashby application form for a job posting, so the job page shows
// whatever questions are set up on that job in Ashby. The API key never leaves
// the server. Env: ASHBY_API_KEY (jobsRead + candidatesWrite).

import { AshbyError, AshbyService } from "../src/ashby.js";

declare const process: { env: Record<string, string | undefined> };

export async function GET(request: Request): Promise<Response> {
  const jobPostingId = new URL(request.url).searchParams.get("jobPostingId");
  if (!jobPostingId) {
    return Response.json({ error: "Missing jobPostingId" }, { status: 400 });
  }

  try {
    const fields = await new AshbyService(process.env.ASHBY_API_KEY).formFields(
      jobPostingId,
    );
    return Response.json(
      { fields },
      // Edge-cached for 5 minutes, so form edits in Ashby show up quickly.
      {
        headers: {
          "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
        },
      },
    );
  } catch (error) {
    if (!(error instanceof AshbyError)) throw error;
    console.error("Ashby jobPosting.info failed", error.status, error.errors);
    return Response.json(
      { error: "Could not load application form" },
      { status: 502 },
    );
  }
}
