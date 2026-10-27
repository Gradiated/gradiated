import type { ComponentPropsWithoutRef, ReactElement } from "react";
import { DocsCodeBlock } from "../docs/DocsCodeBlock";

export const HandbookCodeBlock = ({
  className = "",
  ...props
}: ComponentPropsWithoutRef<"pre">): ReactElement => (
  <DocsCodeBlock className={`gr-handbook-code ${className}`} {...props} />
);
