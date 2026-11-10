const isExternal = (href) =>
  typeof href === "string" && /^https?:\/\//i.test(href);

const isArticle = (path) =>
  typeof path === "string" &&
  path.replace(/\\/g, "/").includes("/content/articles/");

const openInNewTab = (node) => {
  if (
    node.type === "element" &&
    node.tagName === "a" &&
    isExternal(node.properties?.href)
  ) {
    node.properties.target = "_blank";
    node.properties.rel = ["noopener", "noreferrer"];
  }

  for (const child of node.children ?? []) openInNewTab(child);
};

const rehypeArticleExternalLinks = () => (tree, file) => {
  if (!isArticle(file?.path)) return;

  openInNewTab(tree);
};

module.exports = { rehypeArticleExternalLinks };
