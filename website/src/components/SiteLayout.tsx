import { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { PathField } from './PathField';
import { ThemeToggle } from './ThemeToggle';

type SiteLayoutProps = {
  children: ReactNode;
  title: string;
  description?: string;
  home?: boolean;
};

const SiteHeader = (): ReactElement => {
  const location = useLocation();
  const active = location.pathname.startsWith('/products')
    ? 'products'
    : location.pathname.startsWith('/library') || location.pathname.startsWith('/notes')
      ? 'library'
      : 'home';

  return (
    <header className="nav mx-auto flex h-nav max-w-content items-center border-b border-line px-7 max-site:h-nav-mobile max-site:flex-nowrap max-site:gap-0 max-site:px-gutter-mobile">
      <Link className="wordmark inline-flex items-center gap-2.5 font-newsreader text-[20px] font-medium leading-none tracking-wordmark" to="/" aria-label="Gradiated home">
        <img className="wordmark-logo" src="/gradiated-logo-dark-exact.png" alt="" width="25" height="25" />
        gradiated
      </Link>
      <nav className="ml-auto mr-0 flex gap-7 font-libre text-label font-medium uppercase tracking-label max-site:order-none max-site:w-auto max-site:gap-[18px]">
        <Link className={`text-muted ${active === 'home' ? 'active text-ink' : ''} max-site:first:hidden`} to="/">Home</Link>
        <Link className={active === 'products' ? 'active text-ink' : 'text-muted'} to="/products/">Products</Link>
        <Link className={active === 'library' ? 'active text-ink' : 'text-muted'} to="/library/">Library</Link>
      </nav>
    </header>
  );
};

const SiteFooter = (): ReactElement => (
  <footer className="relative mx-auto min-h-0 max-w-content border-t border-line px-7 pb-[42px] pt-[26px] font-libre text-label font-medium uppercase tracking-footer text-muted max-site:flex max-site:flex-wrap max-site:gap-[18px] max-site:px-gutter-mobile max-site:pb-9">
    <Link className="text-ink" to="/">Gradiated</Link>
    <span>© 2026 Gradiated, Inc.</span>
    <Link className="ml-auto text-ink max-site:ml-auto" to="/privacy/">Privacy</Link>
    <ThemeToggle />
  </footer>
);

export const SiteLayout = ({ children, title, description = 'Custom inference paths for open models.', home = false }: SiteLayoutProps): ReactElement => {
  useEffect(() => {
    document.title = title;
    const descriptionElement = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    descriptionElement?.setAttribute('content', description);
  }, [description, title]);

  return (
    <div className={`page-shell relative min-h-screen overflow-hidden${home ? ' home-page' : ''}`}>
      {home && <PathField />}
      <SiteHeader />
      {children}
      <SiteFooter />
    </div>
  );
};
