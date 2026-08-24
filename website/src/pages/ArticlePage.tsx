import { Link } from 'react-router-dom';
import type { ReactElement } from 'react';
import { ThesisContent, WorkingWithUsContent } from '../content';

type ArticlePageProps = {
  kind: 'thesis' | 'working';
};

const articleData = {
  thesis: { date: '2026-07-13', title: 'Thesis', Content: ThesisContent },
  working: { date: '2026-07-15', title: 'Working with us', Content: WorkingWithUsContent },
} as const;

export const ArticlePage = ({ kind }: ArticlePageProps): ReactElement => {
  const article = articleData[kind];
  const Content = article.Content;

  return (
    <main className="article">
      <Link className="eyebrow" to="/library/">← Library</Link>
      <p className="article-date">{article.date}</p>
      <h1>{article.title}</h1>
      <Content />
    </main>
  );
};
