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
  title: string;
};

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
      { external: true, href: "https://status.gradiated.com/", label: "Status" },
    ],
  },
  {
    title: "Company",
    links: [
      { href: "/notes/our-thesis/", label: "Thesis" },
      { href: "/careers/", label: "Careers" },
      { href: "/library/", label: "Library" },
    ],
  },
  {
    title: "Legal",
    links: [
      { href: "/privacy/", label: "Privacy" },
      { href: "/terms/", label: "Terms" },
      { href: "/acceptable-use/", label: "Acceptable use" },
      { href: "/dpa/", label: "DPA" },
      { href: "/subprocessors-security/", label: "Security" },
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
          </ul>
        </nav>
      ))}
    </div>

    <WordmarkField />
    <FooterBar />
  </Module>
);
