import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import type { ReactElement, ReactNode } from "react";
import { SiteLayout } from "./components/SiteLayout";
import { WaitlistDialog } from "./components/WaitlistDialog";
import { jobs } from "./careers";
import { ArticlePage } from "./pages/ArticlePage";
import { AcceptableUsePage } from "./pages/AcceptableUsePage";
import { CareersPage } from "./pages/CareersPage";
import { DpaPage } from "./pages/DpaPage";
import { DocsPage } from "./pages/DocsPage";
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
  home?: boolean;
};

const LayoutRoute = ({
  children,
  ...layoutProps
}: LayoutRouteProps): ReactElement => (
  <SiteLayout {...layoutProps}>{children}</SiteLayout>
);

export const AppRoutes = (): ReactElement => {
  const [waitlistOpen, setWaitlistOpen] = useState(false);

  return (
    <>
      {waitlistOpen && (
        <WaitlistDialog open onClose={() => setWaitlistOpen(false)} />
      )}
      <Routes>
        <Route
          path="/"
          element={
            <LayoutRoute home>
              <HomePage />
            </LayoutRoute>
          }
        />
        <Route
          path="/products/*"
          element={
            <LayoutRoute>
              <ProductsPage onWaitlist={() => setWaitlistOpen(true)} />
            </LayoutRoute>
          }
        />
        <Route
          path="/library/"
          element={
            <LayoutRoute>
              <LibraryPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/careers/"
          element={
            <LayoutRoute>
              <CareersPage />
            </LayoutRoute>
          }
        />
        {jobs.map((job) => (
          <Route
            key={job.slug}
            path={`/careers/${job.slug}/`}
            element={
              <LayoutRoute>
                <JobPage job={job} />
              </LayoutRoute>
            }
          />
        ))}
        <Route
          path="/notes/"
          element={
            <LayoutRoute>
              <NotesPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/notes/our-thesis/"
          element={
            <LayoutRoute>
              <ArticlePage kind="thesis" />
            </LayoutRoute>
          }
        />
        <Route
          path="/notes/working-with-us/"
          element={
            <LayoutRoute>
              <ArticlePage kind="working" />
            </LayoutRoute>
          }
        />
        <Route
          path="/library/handbook/brand/"
          element={
            <LayoutRoute>
              <HandbookPage kind="brand" />
            </LayoutRoute>
          }
        />
        <Route
          path="/library/handbook/values/"
          element={
            <LayoutRoute>
              <HandbookPage kind="values" />
            </LayoutRoute>
          }
        />
        <Route
          path="/docs/*"
          element={
            <LayoutRoute>
              <DocsPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/privacy/"
          element={
            <LayoutRoute>
              <PrivacyPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/terms/"
          element={
            <LayoutRoute>
              <TermsPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/acceptable-use/"
          element={
            <LayoutRoute>
              <AcceptableUsePage />
            </LayoutRoute>
          }
        />
        <Route
          path="/dpa/"
          element={
            <LayoutRoute>
              <DpaPage />
            </LayoutRoute>
          }
        />
        <Route
          path="/subprocessors-security/"
          element={
            <LayoutRoute>
              <SubprocessorsPage />
            </LayoutRoute>
          }
        />
        <Route
          path="*"
          element={
            <LayoutRoute>
              <NotFoundPage />
            </LayoutRoute>
          }
        />
      </Routes>
    </>
  );
};

export const App = (): ReactElement => (
  <BrowserRouter>
    <AppRoutes />
  </BrowserRouter>
);
