import { Fragment, useEffect } from "react";
import type { ReactElement } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { articles } from "./articles";
import { jobs } from "./careers";
import { handbookPages } from "./handbook";
import { models } from "./models";
import { ModelsPage } from "./pages/ModelsPage";
import { LibraryPage } from "./pages/LibraryPage";
import { SystemPage } from "./pages/SystemPage";
import { RailShell } from "./components/design/RailShell";
import { PageMetadata } from "./components/PageMetadata";
import { ModelDetailPage } from "./pages/ModelDetailPage";
import { CareersIndexPage, JobDetailPage } from "./pages/CareersPages";
import { DocsNextPage } from "./pages/DocsNextPage";
import { HardwarePage } from "./pages/HardwarePage";
import { HomePage } from "./pages/HomePage";
import { InferencePage } from "./pages/InferencePage";
import { LEGAL, LegalPage } from "./pages/LegalPages";
import type { LegalSlug } from "./pages/LegalPages";
import { NotesIndexPage } from "./pages/LibraryIndexPage";
import { HandbookPage } from "./pages/HandbookPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ArticleReadingPage } from "./pages/ReadingPages";
import { SandLibraryPage } from "./pages/SandLibraryPage";
import { SAND_TO_THOUGHT_URL } from "./urls";
import { StylePage } from "./pages/StylePage";
import { TrainingPage } from "./pages/TrainingPage";
import { ArtworkGeneratorPage } from "./pages/ArtworkGeneratorPage";
import { AboutPage } from "./pages/AboutPage";

/* No layout wrapper. Every route now carries its own Substrate, Nav and
   Footer, so there is nowhere left for the legacy SiteLayout to be reached
   from — the 404 was the last one. */

const SandJourneyRedirect = (): ReactElement => {
  const { hash } = useLocation();

  return <Navigate replace to={`/sand-to-thought/${hash}`} />;
};

const RouteScrollRestoration = (): null => {
  const { hash, pathname } = useLocation();

  useEffect(() => {
    if (hash) {
      let targetId: string;

      try {
        targetId = decodeURIComponent(hash.slice(1));
      } catch {
        window.scrollTo({ top: 0, left: 0, behavior: "auto" });
        return;
      }

      document.getElementById(targetId)?.scrollIntoView({ block: "start" });
      return;
    }

    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [hash, pathname]);

  return null;
};

/* The rail shell wraps every routed page EXCEPT the doc-rail pages
   (/design wears DocRail) — the two shells are the two faces of the
   same base layer and never nest. */
const Shelled = ({ children }: { children: ReactElement }): ReactElement => (
  <RailShell>{children}</RailShell>
);

export const AppRoutes = (): ReactElement => (
  <Routes>
    {articles.map((article) => (
      <Route
        element={
          <Shelled>
            <ArticleReadingPage article={article} />
          </Shelled>
        }
        key={article.path}
        path={article.path}
      />
    ))}
    {/* No SiteLayout: the homepage carries its own Nav and Footer now, like
        every other page on the design system. The legacy layout is what was
        giving it the old nav and the old footer. */}
    <Route
      element={
        <Shelled>
          <HomePage />
        </Shelled>
      }
      path="/"
    />
    <Route element={<SystemPage />} path="/design" />
    <Route
      element={
        <Shelled>
          <AboutPage />
        </Shelled>
      }
      path="/about/"
    />
    <Route
      element={
        <Shelled>
          <LibraryPage />
        </Shelled>
      }
      path="/library/"
    />
    <Route
      element={
        <Shelled>
          <SandLibraryPage />
        </Shelled>
      }
      path={SAND_TO_THOUGHT_URL}
    />
    <Route
      element={
        <Shelled>
          <SandJourneyRedirect />
        </Shelled>
      }
      path="/library/how-to-get-an-answer-out-of-sand/"
    />
    <Route
      element={
        <Shelled>
          <NotesIndexPage />
        </Shelled>
      }
      path="/notes/"
    />
    <Route
      element={
        <Shelled>
          <HandbookPage />
        </Shelled>
      }
      path="/handbook/"
    />
    <Route element={<Navigate replace to="/handbook/" />} path="/methods/" />
    <Route
      element={
        <Shelled>
          <CareersIndexPage />
        </Shelled>
      }
      path="/careers/"
    />
    {jobs.map((job) => (
      <Route
        element={
          <Shelled>
            <JobDetailPage job={job} />
          </Shelled>
        }
        key={job.slug}
        path={`/careers/${job.slug}/`}
      />
    ))}
    {handbookPages.map((page) => (
      <Fragment key={page.slug}>
        <Route
          element={
            <Shelled>
              <HandbookPage slug={page.slug} />
            </Shelled>
          }
          path={`/handbook/${page.slug}/`}
        />
        <Route
          element={<Navigate replace to={`/handbook/${page.slug}/`} />}
          path={`/methods/${page.slug}/`}
        />
        <Route
          element={<Navigate replace to={`/handbook/${page.slug}/`} />}
          path={`/library/method/${page.slug}/`}
        />
      </Fragment>
    ))}
    <Route
      element={
        <Shelled>
          <DocsNextPage />
        </Shelled>
      }
      path="/docs/*"
    />
    {Object.keys(LEGAL).map((slug) => (
      <Route
        element={
          <Shelled>
            <LegalPage slug={slug as LegalSlug} />
          </Shelled>
        }
        key={`legal-${slug}`}
        path={`/${slug}/`}
      />
    ))}
    <Route
      element={
        <Shelled>
          <InferencePage />
        </Shelled>
      }
      path="/inference/"
    />
    <Route
      element={
        <Shelled>
          <TrainingPage />
        </Shelled>
      }
      path="/training/"
    />
    <Route
      element={
        <Shelled>
          <HardwarePage />
        </Shelled>
      }
      path="/hardware/"
    />
    <Route
      element={
        <Shelled>
          <ArtworkGeneratorPage />
        </Shelled>
      }
      path="/artwork-generator/"
    />
    <Route
      element={
        <Shelled>
          <ModelsPage />
        </Shelled>
      }
      path="/models/"
    />
    {models.map((model) => (
      <Route
        element={
          <Shelled>
            <ModelDetailPage model={model} />
          </Shelled>
        }
        key={model.slug}
        path={`/models/${model.slug}/`}
      />
    ))}
    <Route
      element={
        <Shelled>
          <StylePage />
        </Shelled>
      }
      path="/style/"
    />
    <Route
      element={
        <Shelled>
          <NotFoundPage />
        </Shelled>
      }
      path="*"
    />
  </Routes>
);

export const App = (): ReactElement => (
  <BrowserRouter>
    <RouteScrollRestoration />
    <PageMetadata />
    <AppRoutes />
  </BrowserRouter>
);
