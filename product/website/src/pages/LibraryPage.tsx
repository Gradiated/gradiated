import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import type { ReactElement } from "react";
import { articles } from "../articles";
import { handbookPages } from "../handbook";

export const LibraryPage = (): ReactElement => (
  <main className="notes library">
    <section className="library-section" aria-labelledby="writing-heading">
      <h1 id="writing-heading">Writing</h1>
      <div className="post-list">
        {articles.map((note) => (
          <Link className="post-row" key={note.path} to={note.path}>
            <span>{note.status === "draft" ? "Draft" : note.publishedAt}</span>
            <div>
              <h2>{note.title}</h2>
              {note.description ? <p>{note.description}</p> : null}
            </div>
            <ArrowUpRight
              aria-hidden="true"
              className="post-row-icon"
              strokeWidth={1.5}
            />
          </Link>
        ))}
      </div>
    </section>
    <section
      className="library-section library-handbook"
      aria-labelledby="handbook-heading"
    >
      <h2 id="handbook-heading">Handbook</h2>
      <div className="post-list">
        {handbookPages.map((page) => (
          <Link
            className="post-row"
            key={page.slug}
            to={`/handbook/${page.slug}/`}
          >
            <span>{page.section}</span>
            <div>
              <h2>{page.title}</h2>
            </div>
            <ArrowUpRight
              aria-hidden="true"
              className="post-row-icon"
              strokeWidth={1.5}
            />
          </Link>
        ))}
      </div>
    </section>
  </main>
);
