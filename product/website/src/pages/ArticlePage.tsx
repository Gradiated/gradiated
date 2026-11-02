import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import type { ReactElement, ComponentType } from "react";
import type { Article } from "../articles";
import {
  DocsCodeBlock,
  DocsInlineCode,
} from "../components/docs/DocsCodeBlock";

const content = import.meta.glob<{
  default: ComponentType<Record<string, unknown>>;
}>("../../content/articles/*.mdx", { eager: true });

export const ArticlePage = ({
  article,
}: {
  article: Article;
}): ReactElement => {
  const Content = content[`../${article.file}`]?.default;
  if (!Content) throw new Error(`Missing article component: ${article.file}`);
  return (
    <main className="article">
      <Link className="eyebrow article-back-link" to="/notes/">
        <ArrowLeft aria-hidden="true" className="h-3 w-3" strokeWidth={1.5} />
        <span>Library</span>
      </Link>
      <p className="article-date">
        {article.status === "draft" ? "Draft · " : ""}
        <time dateTime={article.publishedAt}>{article.publishedAt}</time>
      </p>
      <h1>{article.title}</h1>
      <Content components={{ code: DocsInlineCode, pre: DocsCodeBlock }} />
    </main>
  );
};
