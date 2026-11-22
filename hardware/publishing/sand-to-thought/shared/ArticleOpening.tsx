import type { ReactNode } from "react";
import "./article-opening.css";

export const ArticleOpening = ({ author, children }: {
  author?: string;
  children: ReactNode;
}) => {
  if (!author) return <>{children}</>;

  return (
    <>
      <p className="sand-mobile-author">{author}</p>
      {children}
    </>
  );
};
