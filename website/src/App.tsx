import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { SiteLayout } from './components/SiteLayout';
import { WaitlistDialog } from './components/WaitlistDialog';
import { ArticlePage } from './pages/ArticlePage';
import { HandbookPage } from './pages/HandbookPage';
import { HomePage } from './pages/HomePage';
import { LibraryPage } from './pages/LibraryPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { NotesPage } from './pages/NotesPage';
import { PrivacyPage } from './pages/PrivacyPage';
import { ProductsPage } from './pages/ProductsPage';

type LayoutRouteProps = {
  children: ReactNode;
  title: string;
  description?: string;
  home?: boolean;
};

const LayoutRoute = ({ children, ...layoutProps }: LayoutRouteProps): ReactElement => (
  <SiteLayout {...layoutProps}>{children}</SiteLayout>
);

export const App = (): ReactElement => {
  const [waitlistOpen, setWaitlistOpen] = useState(false);

  return (
    <BrowserRouter>
      <WaitlistDialog open={waitlistOpen} onClose={() => setWaitlistOpen(false)} />
      <Routes>
        <Route path="/" element={<LayoutRoute title="Gradiated — Custom inference paths for open models." home><HomePage onWaitlist={() => setWaitlistOpen(true)} /></LayoutRoute>} />
        <Route path="/products/*" element={<LayoutRoute title="Products — Gradiated" description="Gradiated inference products."><ProductsPage onWaitlist={() => setWaitlistOpen(true)} /></LayoutRoute>} />
        <Route path="/library/" element={<LayoutRoute title="Library — Gradiated" description="Writing and the Gradiated method."><LibraryPage /></LayoutRoute>} />
        <Route path="/notes/" element={<LayoutRoute title="Notes — Gradiated"><NotesPage /></LayoutRoute>} />
        <Route path="/notes/our-thesis/" element={<LayoutRoute title="Thesis — Gradiated"><ArticlePage kind="thesis" /></LayoutRoute>} />
        <Route path="/notes/working-with-us/" element={<LayoutRoute title="Working with us — Gradiated"><ArticlePage kind="working" /></LayoutRoute>} />
        <Route path="/library/handbook/brand/" element={<LayoutRoute title="Brand — Gradiated Method" description="The Gradiated brand principles."><HandbookPage kind="brand" /></LayoutRoute>} />
        <Route path="/library/handbook/values/" element={<LayoutRoute title="Values — Gradiated Method" description="The values in the Gradiated method."><HandbookPage kind="values" /></LayoutRoute>} />
        <Route path="/privacy/" element={<LayoutRoute title="Privacy — Gradiated"><PrivacyPage /></LayoutRoute>} />
        <Route path="*" element={<LayoutRoute title="Not found — Gradiated"><NotFoundPage /></LayoutRoute>} />
      </Routes>
    </BrowserRouter>
  );
};
