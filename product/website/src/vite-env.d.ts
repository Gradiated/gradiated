/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly PREVIEW: boolean;
}

declare module "*.md?sand-article" {
  const html: string;
  export default html;
}
