/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly PREVIEW: boolean;
}

declare module "*.md?sand-article" {
  export const contents: { id: string; label: string }[];
  const html: string;
  export default html;
}
