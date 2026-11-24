import type { ReactElement } from "react";
import { FooterBar } from "./FooterBar";
import { Logo } from "./Logo";
import { Module } from "./Module";
import { WordmarkField } from "./WordmarkField";

/**
 * The footer: link columns, then the chip-assembled wordmark as the last thing
 * on the page.
 *
 * A full-bleed module: the surface runs the whole viewport, while the links and
 * the wordmark stay on the band grid — so the footer's type still aligns with
 * every section above it and only the ground extends. The wordmark takes the
 * band's full width, which is what makes it read as a closing statement rather
 * than an element on the page.
 *
 * Built from Module rather than a hand-rolled <section> so it inherits the
 * bleed behaviour, the seam line and the entrance cascade for free.
 */

type FooterColumn = {
  links: { external?: boolean; href: string; label: string }[];
  social?: boolean;
  title: string;
};

/* Brand marks from Simple Icons (CC0), drawn on a 24-unit square. */
const SOCIAL_LINKS = [
  {
    href: "https://www.linkedin.com/company/gradiated",
    label: "Gradiated on LinkedIn",
    path: "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
  },
  {
    href: "https://x.com/gradiated",
    label: "Gradiated on X",
    path: "M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z",
  },
];

const COLUMNS: FooterColumn[] = [
  {
    title: "Product",
    links: [
      { href: "/training/", label: "Training" },
      { href: "/inference/", label: "Inference" },
      { href: "/docs/service-tiers/", label: "Service tiers" },
      { href: "/docs/models-pricing/", label: "Models and pricing" },
    ],
  },
  {
    title: "Developers",
    links: [
      { href: "/docs/quickstart/", label: "Quickstart" },
      { href: "/docs/api-reference/", label: "API reference" },
      { href: "/docs/errors/", label: "Errors" },
      /* Status is a service Gradiated runs, not a page this site renders — a
         reader looking for it is a developer checking whether the API is up,
         so it belongs here rather than in Legal. */
      {
        external: true,
        href: "https://status.gradiated.com/",
        label: "Status",
      },
    ],
  },
  {
    title: "Company",
    social: true,
    links: [
      { href: "/about/", label: "About" },
      { href: "/library/our-thesis/", label: "Thesis" },
      { href: "/careers/", label: "Careers" },
      { href: "/library/", label: "Library" },
      { href: "/handbook/", label: "Handbook" },
    ],
  },
  {
    title: "Legal",
    links: [
      { href: "/privacy/", label: "Privacy" },
      { href: "/terms/", label: "Terms" },
      { href: "/sla/", label: "SLA" },
      { href: "/acceptable-use/", label: "Acceptable use" },
      { href: "/dpa/", label: "DPA" },
      { href: "/subprocessors/", label: "Subprocessors" },
    ],
  },
];

export const Footer = ({ index = 0 }: { index?: number }): ReactElement => (
  <Module bleed className="gr-footer" index={index}>
    {/* Mark hard left, link columns packed right, a flexible valley between.
        Not built on Columns: that grid divides the band evenly, and four even
        columns plus a mark leaves the link text too narrow. Here the valley is
        the only flexible track, so it absorbs whatever the fixed parts do not
        use — see .gr-footer-top. */}
    <div className="gr-footer-top">
      <a aria-label="Gradiated home" className="gr-footer-mark" href="/">
        <Logo mark />
      </a>

      {COLUMNS.map((column) => (
        <nav aria-label={column.title} key={column.title}>
          <p className="gr-label">{column.title}</p>
          <ul className="gr-footer-links">
            {column.links.map((link) => (
              <li key={link.href}>
                <a
                  className="gr-link gr-footer-link"
                  href={link.href}
                  /* Leaves the site, so it opens away from it — and carries
                     noreferrer, which is what the legacy footer did too. */
                  rel={link.external ? "noreferrer" : undefined}
                  target={link.external ? "_blank" : undefined}
                >
                  {link.label}
                </a>
              </li>
            ))}
            {column.social && (
              <li className="gr-footer-social">
                {SOCIAL_LINKS.map((link) => (
                  <a
                    aria-label={link.label}
                    className="gr-footer-social-link"
                    href={link.href}
                    key={link.href}
                    rel="noreferrer"
                    target="_blank"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24">
                      <path d={link.path} fill="currentColor" />
                    </svg>
                  </a>
                ))}
              </li>
            )}
          </ul>
        </nav>
      ))}
    </div>

    <WordmarkField />
    <FooterBar />
  </Module>
);
