import type { ComponentType, ReactElement } from "react";
import {
  Band,
  Footer,
  Module,
  Nav,
  Reading,
  Substrate,
} from "../components/design";
import { authorOf } from "../articles";
import type { Article } from "../articles";
import {
  DocsCodeBlock,
  DocsInlineCode,
} from "../components/docs/DocsCodeBlock";
import { displayDate, storyAt } from "../library-stories";
import "../styles/index.css";

const articleContent = import.meta.glob<{
  default: ComponentType<Record<string, unknown>>;
}>("../../content/articles/*.mdx", { eager: true });

export const ArticleReadingPage = ({
  article,
}: {
  article: Article;
}): ReactElement => {
  const Content = articleContent[`../${article.file}`]?.default;
  if (!Content) throw new Error(`Missing article component: ${article.file}`);

  if (article.layout === "journey") {
    return (
      <Substrate>
        <Nav />
        <Content article={article} />
        <Band>
          <Footer index={1} />
        </Band>
      </Substrate>
    );
  }

  return (
    <Substrate>
      <Nav />
      <Band>
        <Module className="gr-module--top" index={0}>
          <Reading
            author={article.author}
            authorHref={authorOf(article)?.path}
            authorTitle={
              article.authorTitle ??
              // "Technical Staff – Hardware" is "Technical Staff" in a byline.
              authorOf(article)?.role.split(/\s+[–—-]\s+/)[0]
            }
            byline={
              article.status === "draft"
                ? undefined
                : displayDate(article.publishedAt)
            }
            bylineDateTime={
              article.status === "draft" ? undefined : article.publishedAt
            }
            art={storyAt(article.path)?.art?.tall}
            cover={storyAt(article.path)?.cover}
            id={article.path.split("/").filter(Boolean).pop()}
            lede={article.description}
            links={article.links}
            note={article.note}
            tags={[article.category === "hardware" ? "Hardware" : "Notes"]}
            title={article.title}
          >
            <Content
              components={{ code: DocsInlineCode, pre: DocsCodeBlock }}
            />
          </Reading>
        </Module>
      </Band>
      <Band>
        <Footer index={1} />
      </Band>
    </Substrate>
  );
};
