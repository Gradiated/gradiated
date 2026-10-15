import { buildArticleRegistry } from "./article-metadata";

export const articles = buildArticleRegistry(
  import.meta.glob<string>("../content/articles/*.mdx", {
    eager: true,
    query: "?raw",
    import: "default",
  }),
  import.meta.env.DEV || import.meta.env.PREVIEW,
);
export type Article = (typeof articles)[number];
