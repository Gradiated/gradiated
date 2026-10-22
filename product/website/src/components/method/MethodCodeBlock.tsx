import type { ComponentPropsWithoutRef, ReactElement } from "react";
import { DocsCodeBlock } from "../docs/DocsCodeBlock";

export const MethodCodeBlock = ({
  className = "",
  ...props
}: ComponentPropsWithoutRef<"pre">): ReactElement => (
  <DocsCodeBlock className={`gr-method-code ${className}`} {...props} />
);
