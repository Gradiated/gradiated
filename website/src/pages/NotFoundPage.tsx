import { Link } from 'react-router-dom';
import type { ReactElement } from 'react';

export const NotFoundPage = (): ReactElement => (
  <main className="not-found">
    <p>404 / An unanswered question</p>
    <h1>What were you looking for?</h1>
    <span>The path ended here.</span>
    <nav><Link to="/">Return home →</Link><Link to="/notes/our-thesis/">Read the thesis →</Link><a href="mailto:signal@gradiated.com">Ask us directly →</a></nav>
  </main>
);
