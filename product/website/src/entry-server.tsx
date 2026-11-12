import { StrictMode } from "react";
import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router-dom";

import { AppRoutes } from "./App";
import {
  formatPageTitle,
  getAllPagePaths,
  getPageMetadata,
  getStructuredData,
} from "./metadata";

export const renderPage = (pathname: string): string =>
  renderToString(
    <StrictMode>
      <StaticRouter location={pathname}>
        <AppRoutes />
      </StaticRouter>
    </StrictMode>,
  );

export const getSeoPages = () =>
  getAllPagePaths().map((path) => ({
    metadata: getPageMetadata(path),
    path,
    structuredData: getStructuredData(path),
    title: formatPageTitle(getPageMetadata(path).title),
  }));

export const getNotFoundPage = () => ({
  metadata: getPageMetadata("/404/"),
  path: "/404/",
  structuredData: [],
  title: formatPageTitle(getPageMetadata("/404/").title),
});
