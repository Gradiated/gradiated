import type { ReactElement } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { articles } from "./articles";
import { jobs } from "./careers";
import { methodPages } from "./method";
import { models } from "./models";
import { ModelDetailPage } from "./pages/ModelDetailPage";
import { CareersIndexPage, JobDetailPage } from "./pages/CareersPages";
import { DocsNextPage } from "./pages/DocsNextPage";
import { HardwarePage } from "./pages/HardwarePage";
import { HomePage } from "./pages/HomePage";
import { InferencePage } from "./pages/InferencePage";
import { LEGAL, LegalPage } from "./pages/LegalPages";
import type { LegalSlug } from "./pages/LegalPages";
import { LibraryIndexPage } from "./pages/LibraryIndexPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ArticleReadingPage, MethodReadingPage } from "./pages/ReadingPages";
import { StylePage } from "./pages/StylePage";
import { TrainingPage } from "./pages/TrainingPage";
import { ArtworkGeneratorPage } from "./pages/ArtworkGeneratorPage";

/* No layout wrapper. Every route now carries its own Substrate, Nav and
   Footer, so there is nowhere left for the legacy SiteLayout to be reached
   from — the 404 was the last one. */

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
    <Route element={<LibraryIndexPage />} path="/library/" />
    <Route
      element={<LibraryIndexPage initialFilter="notes" />}
      path="/notes/"
    />
    <Route element={<CareersIndexPage />} path="/careers/" />
    {jobs.map((job) => (
      <Route
        element={<JobDetailPage job={job} />}
        key={job.slug}
        path={`/careers/${job.slug}/`}
      />
    ))}
    {methodPages.map((page) => (
      <Route
        element={<MethodReadingPage slug={page.slug} />}
        key={page.slug}
        path={`/library/method/${page.slug}/`}
      />
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
    <AppRoutes />
  </BrowserRouter>
);
