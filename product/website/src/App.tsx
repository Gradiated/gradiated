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

const LibraryRedirect = (): ReactElement => {
  const { search } = useLocation();
  const destination = new URLSearchParams(search).get("show");
  const target =
    destination === "methods" || destination === "handbook"
      ? "/handbook/"
      : "/notes/";

  useEffect(() => {
    window.location.replace(target);
  }, [target]);

  /* Keep any served fallback stable until the query-based redirect runs. */
  return <NotesIndexPage />;
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

export const AppRoutes = (): ReactElement => (
  <Routes>
    {articles.map((article) => (
      <Route
        element={<ArticleReadingPage article={article} />}
        key={article.path}
        path={article.path}
      />
    ))}
    {/* No SiteLayout: the homepage carries its own Nav and Footer now, like
        every other page on the design system. The legacy layout is what was
        giving it the old nav and the old footer. */}
    <Route element={<HomePage />} path="/" />
    <Route element={<AboutPage />} path="/about/" />
    <Route element={<LibraryRedirect />} path="/library/" />
    <Route element={<SandLibraryPage />} path={SAND_TO_THOUGHT_URL} />
    <Route
      element={<SandJourneyRedirect />}
      path="/library/how-to-get-an-answer-out-of-sand/"
    />
    <Route element={<NotesIndexPage />} path="/notes/" />
    <Route element={<HandbookPage />} path="/handbook/" />
    <Route element={<Navigate replace to="/handbook/" />} path="/methods/" />
    <Route element={<CareersIndexPage />} path="/careers/" />
    {jobs.map((job) => (
      <Route
        element={<JobDetailPage job={job} />}
        key={job.slug}
        path={`/careers/${job.slug}/`}
      />
    ))}
    {handbookPages.map((page) => (
      <Fragment key={page.slug}>
        <Route
          element={<HandbookPage slug={page.slug} />}
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
    <Route element={<DocsNextPage />} path="/docs/*" />
    {Object.keys(LEGAL).map((slug) => (
      <Route
        element={<LegalPage slug={slug as LegalSlug} />}
        key={`legal-${slug}`}
        path={`/${slug}/`}
      />
    ))}
    <Route element={<InferencePage />} path="/inference/" />
    <Route element={<TrainingPage />} path="/training/" />
    <Route element={<HardwarePage />} path="/hardware/" />
    <Route element={<ArtworkGeneratorPage />} path="/artwork-generator/" />
    <Route element={<ModelsPage />} path="/models/" />
    {models.map((model) => (
      <Route
        element={<ModelDetailPage model={model} />}
        key={model.slug}
        path={`/models/${model.slug}/`}
      />
    ))}
    <Route element={<StylePage />} path="/style/" />
    <Route element={<NotFoundPage />} path="*" />
  </Routes>
);

export const App = (): ReactElement => (
  <BrowserRouter>
    <RouteScrollRestoration />
    <AppRoutes />
  </BrowserRouter>
);
