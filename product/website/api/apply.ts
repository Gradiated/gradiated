// POST /api/apply  (multipart/form-data from src/components/ApplyForm.tsx)
//
// Forwards an application to Ashby, same approach as posthog.com's
// api/apply.js. The answer encoding is documented in src/ashby.ts.
// Env: ASHBY_API_KEY (jobsRead + candidatesWrite).

import { AshbyError, AshbyService } from "../src/ashby.js";

declare const process: { env: Record<string, string | undefined> };

const fail = (error: string, status: number): Response =>
  Response.json({ success: false, error }, { status });

export async function POST(request: Request): Promise<Response> {
  let answers: FormData;
  try {
    answers = await request.formData();
  } catch {
    return fail("Bad form data", 400);
  }

  const jobPostingId = answers.get("jobPostingId");
  if (typeof jobPostingId !== "string" || !jobPostingId) {
    return fail("Missing jobPostingId", 400);
  }

  try {
    const result = await new AshbyService(
      process.env.ASHBY_API_KEY,
    ).submitApplication(jobPostingId, answers);
    return Response.json({ success: true, ...result });
  } catch (error) {
    if (!(error instanceof AshbyError)) throw error;
    // Status and error codes only, never the candidate's answers.
    console.error(
      "Ashby applicationForm.submit failed",
      error.status,
      error.errors,
    );
    // Ashby answered but rejected the application: 422. Ashby itself failed: 502.
    const ashbyAnswered = error.status >= 200 && error.status < 300;
    return fail("Failed to submit application", ashbyAnswered ? 422 : 502);
  }
}
