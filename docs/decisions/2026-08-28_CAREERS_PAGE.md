# Careers page implementation

- status: implemented
- date: 2026-08-28

## Decision

The public website has one careers index and three broad job listings:

- Founding Inference Research Engineer;
- Head of Silicon;
- Founding Silicon Engineer.

The roles support the first ten hires without a fixed allocation. The copy
states the tokens-per-joule direction, the generalist standard, the pay range,
the office schedule, and clear exclusions for each role.

## Files and routes

- `product/website/src/careers.ts` owns the role metadata and job copy.
- `product/website/src/pages/CareersPage.tsx` owns `/careers/`.
- `product/website/src/pages/JobPage.tsx` owns the shared job-page structure.
- `product/website/src/App.tsx` generates `/careers/<slug>/` routes.
- `product/website/src/components/SiteLayout.tsx` links to careers from the
  header and footer.
- `product/website/src/pages/HomePage.tsx` links the hiring feature to the
  careers index.

Applications use `team@gradiated.com` through a `mailto:` link. The feature
does not need an external service or a credential.

## Run and verify

From `product/`:

```bash
pnpm --dir website dev
pnpm --dir website build
python3 ../tools/devex/check.py
git diff --check
```

The implementation passed the website type check and production build. It also
passed the DevEx check, Prettier check, and Git whitespace check. Chromium
visual checks passed at 1440 pixels and 390 pixels for the careers index and a
job page.

## Known limits

- Applications use email. There is no applicant tracking system or form.
- Job content lives in TypeScript. There is no content management interface.
- The production build reports the existing warning for a JavaScript chunk
  larger than 500 kB.
- The pay and work terms need a final company and employment-law review before
  publication.

## Next safe action

Review the public copy. Then deploy the website through the normal Vercel
workflow.
