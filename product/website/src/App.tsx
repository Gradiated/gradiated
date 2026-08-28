import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";
import { SiteLayout } from "./components/SiteLayout";
import { WaitlistDialog } from "./components/WaitlistDialog";
import { jobs } from "./careers";
import { ArticlePage } from "./pages/ArticlePage";
import { AcceptableUsePage } from "./pages/AcceptableUsePage";
import { CareersPage } from "./pages/CareersPage";
import { DocsPage } from "./pages/DocsPage";
import { DpaPage } from "./pages/DpaPage";
import { HandbookPage } from "./pages/HandbookPage";
import { HomePage } from "./pages/HomePage";
import { JobPage } from "./pages/JobPage";
import { LibraryPage } from "./pages/LibraryPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { NotesPage } from "./pages/NotesPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { ProductsPage } from "./pages/ProductsPage";
import { SubprocessorsPage } from "./pages/SubprocessorsPage";
import { TermsPage } from "./pages/TermsPage";

type LayoutRouteProps = {
  children: ReactNode;
  title: string;
  description?: string;
  home?: boolean;
};

const LayoutRoute = ({
  children,
  ...layoutProps
}: LayoutRouteProps): ReactElement => (
  <SiteLayout {...layoutProps}>{children}</SiteLayout>
);

export const App = (): ReactElement => {
  const [waitlistOpen, setWaitlistOpen] = useState(false);

  return (
    <BrowserRouter>
      <WaitlistDialog
        open={waitlistOpen}
        onClose={() => setWaitlistOpen(false)}
      />
      <Routes>
        <Route
          path="/"
          element={
            <LayoutRoute
              title="Gradiated — Custom inference paths for open models."
              home
            >
              <HomePage />
            </LayoutRoute>
          }
        />
        <Route
          path="/products/*"
          element={
            <LayoutRoute
              title="Products — Gradiated"
              description="Gradiated inference products."
            >
              <ProductsPage onWaitlist={() => setWaitlistOpen(true)} />
            </LayoutRoute>
          }
        />
        <Route
          path="/library/"
          element={
            <LayoutRoute
              title="Library — Gradiated"
              description="Writing and the Gradiated method."
            >
              <LibraryPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/careers/"
          element={
            <LayoutRoute
              title="Careers — Gradiated"
              description="Build inference software and silicon at Gradiated."
            >
              <CareersPage />
            </LayoutRoute>
          }
        />
        {jobs.map((job) => (
          <Route
            key={job.slug}
            path={`/careers/${job.slug}/`}
            element={
              <LayoutRoute
                title={`${job.title} — Gradiated`}
                description={job.summary}
              >
                <JobPage job={job} />
              </LayoutRoute>
            }
          />
        ))}
        <Route
          path="/notes/"
          element={
            <LayoutRoute title="Notes — Gradiated">
              <NotesPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/notes/our-thesis/"
          element={
            <LayoutRoute title="Thesis — Gradiated">
              <ArticlePage kind="thesis" />
            </LayoutRoute>
          }
        />
        <Route
          path="/notes/working-with-us/"
          element={
            <LayoutRoute title="Working with us — Gradiated">
              <ArticlePage kind="working" />
            </LayoutRoute>
          }
        />
        <Route
          path="/library/handbook/brand/"
          element={
            <LayoutRoute
              title="Brand — Gradiated Method"
              description="The Gradiated brand principles."
            >
              <HandbookPage kind="brand" />
            </LayoutRoute>
          }
        />
        <Route
          path="/library/handbook/values/"
          element={
            <LayoutRoute
              title="Values — Gradiated Method"
              description="The values in the Gradiated method."
            >
              <HandbookPage kind="values" />
            </LayoutRoute>
          }
        />
        <Route
          path="/docs/"
          element={
            <LayoutRoute
              title="Docs — Gradiated"
              description="Use Gradiated inference in your tools and applications."
            >
              <DocsPage page="index" />
            </LayoutRoute>
          }
        />
        <Route
          path="/docs/quickstart/"
          element={
            <LayoutRoute
              title="Quickstart — Gradiated Docs"
              description="Make your first Gradiated inference request."
            >
              <DocsPage page="quickstart" />
            </LayoutRoute>
          }
        />
        <Route
          path="/docs/opencode/"
          element={
            <LayoutRoute
              title="OpenCode — Gradiated Docs"
              description="Use Gradiated inference in OpenCode."
            >
              <DocsPage page="opencode" />
            </LayoutRoute>
          }
        />
        <Route
          path="/docs/codex/"
          element={
            <LayoutRoute
              title="Codex — Gradiated Docs"
              description="Use Gradiated inference in Codex."
            >
              <DocsPage page="codex" />
            </LayoutRoute>
          }
        />
        <Route
          path="/docs/claude-code/"
          element={
            <LayoutRoute
              title="Claude Code — Gradiated Docs"
              description="Use Gradiated inference in Claude Code."
            >
              <DocsPage page="claude-code" />
            </LayoutRoute>
          }
        />
        <Route
          path="/docs/api/"
          element={
            <LayoutRoute
              title="Chat Completions API — Gradiated Docs"
              description="Call Gradiated inference through the OpenAI-compatible API."
            >
              <DocsPage page="api" />
            </LayoutRoute>
          }
        />
        <Route
          path="/privacy/"
          element={
            <LayoutRoute title="Privacy — Gradiated">
              <PrivacyPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/terms/"
          element={
            <LayoutRoute title="Terms — Gradiated">
              <TermsPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/acceptable-use/"
          element={
            <LayoutRoute title="Acceptable use — Gradiated">
              <AcceptableUsePage />
            </LayoutRoute>
          }
        />
        <Route
          path="/dpa/"
          element={
            <LayoutRoute title="DPA — Gradiated">
              <DpaPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/subprocessors-security/"
          element={
            <LayoutRoute title="Security — Gradiated">
              <SubprocessorsPage />
            </LayoutRoute>
          }
        />
        <Route
          path="*"
          element={
            <LayoutRoute title="Not found — Gradiated">
              <NotFoundPage />
            </LayoutRoute>
          }
        />
      </Routes>
    </BrowserRouter>
  );
};
