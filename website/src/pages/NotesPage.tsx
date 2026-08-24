import { Link } from 'react-router-dom';
import type { ReactElement } from 'react';
import { notes } from '../content';

export const NotesPage = (): ReactElement => (
  <main className="notes">
    <h1>Ideas from the edge of inference.</h1>
    <div className="post-list">
      {notes.map((note) => (
        <Link className="post-row" key={note.slug} to={`/notes/${note.slug}/`}>
          <span>{note.date}</span><div><h2>{note.title}</h2><p>{note.description}</p></div><b>↗</b>
        </Link>
      ))}
    </div>
  </main>
);
