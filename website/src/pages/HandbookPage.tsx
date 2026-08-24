import { Link } from 'react-router-dom';
import type { ReactElement } from 'react';
import { BrandContent, ValuesContent } from '../content';

type HandbookPageProps = {
  kind: 'brand' | 'values';
};

const handbookData = {
  brand: { title: 'Brand', description: 'The Gradiated brand principles.', Content: BrandContent },
  values: { title: 'Values', description: 'The values in the Gradiated method.', Content: ValuesContent },
} as const;

export const HandbookPage = ({ kind }: HandbookPageProps): ReactElement => {
  const handbook = handbookData[kind];
  const Content = handbook.Content;

  return (
    <main className="article handbook-article">
      <Link className="eyebrow" to="/library/">← Library</Link>
      <h1>{handbook.title}</h1>
      <Content />
    </main>
  );
};
