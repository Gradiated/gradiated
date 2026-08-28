import { Link } from "react-router-dom";
import type { ReactElement } from "react";
import { notes } from "../content";

export const LibraryPage = (): ReactElement => (
  <main className="notes library">
    <section className="library-section" aria-labelledby="writing-heading">
      <h1 id="writing-heading">Writing</h1>
      <div className="post-list">
        {notes.map((note) => (
          <Link
            className="post-row"
            key={note.slug}
            to={`/notes/${note.slug}/`}
          >
            <span>{note.date}</span>
            <div>
              <h2>{note.title}</h2>
              <p>{note.description}</p>
            </div>
            <b>↗</b>
          </Link>
        ))}
      </div>
    </section>
    <section
      className="library-section library-handbook"
      aria-labelledby="method-heading"
    >
      <h2 id="method-heading">Method</h2>
      <div className="post-list">
        <Link className="post-row" to="/library/handbook/values/">
          <span>Company</span>
          <div>
            <h2>Values</h2>
            <p>Depth and meritocracy.</p>
          </div>
          <b>↗</b>
        </Link>
        <Link className="post-row" to="/library/handbook/brand/">
          <span>Market</span>
          <div>
            <h2>Brand</h2>
            <p>Everything is considered.</p>
          </div>
          <b>↗</b>
        </Link>
      </div>
    </section>
  </main>
);
