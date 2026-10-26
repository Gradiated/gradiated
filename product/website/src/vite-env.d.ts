/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly PREVIEW: boolean;
}

declare module "*.md?sand-article" {
  export const contents: { id: string; label: string }[];
  const html: string;
  export default html;
}

declare module "*.md?fabrication-article" {
  const article: {
    introduction: string;
    scenes: { key: string; html: string }[];
    bibliography: string;
  };
  export default article;
}
