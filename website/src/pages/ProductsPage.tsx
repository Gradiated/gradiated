import { ProductSection } from '../components/ProductSection';
import type { ReactElement } from 'react';

type ProductsPageProps = {
  onWaitlist: () => void;
};

export const ProductsPage = ({ onWaitlist }: ProductsPageProps): ReactElement => (
  <main className="products-page">
    <section className="products-intro">
      <p className="eyebrow">Products</p>
      <h1>Inference.</h1>
    </section>
    <ProductSection onWaitlist={onWaitlist} />
  </main>
);
