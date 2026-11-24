import { buildArticleRegistry } from "./article-metadata";
import { team } from "./team";

export const articles = buildArticleRegistry(
  import.meta.glob<string>("../content/articles/*.mdx", {
    eager: true,
    query: "?raw",
    import: "default",
  }),
  import.meta.env.DEV || import.meta.env.PREVIEW,
);
export type Article = (typeof articles)[number];

// The author's profile lists the piece, so an author must be on the team.
const unknown = articles.filter(
  (article) => !team.some((member) => member.name === article.author),
);
if (unknown.length > 0) {
  throw new Error(
    `Library pieces need an \`author\` named exactly as in content/team/: ${unknown
      .map((article) => `${article.path} ("${article.author}")`)
      .join(", ")}.`,
  );
}

export const authorOf = (article: Article) =>
  team.find((member) => member.name === article.author);
