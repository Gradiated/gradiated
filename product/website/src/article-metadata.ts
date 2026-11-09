import { parse } from "yaml";
import { z } from "zod";

const date = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .refine((value) => {
    const parsed = new Date(`${value}T00:00:00Z`);
    return (
      Number.isFinite(parsed.getTime()) &&
      parsed.toISOString().slice(0, 10) === value
    );
  }, "Use a valid calendar date");
const schema = z
  .object({
    title: z.string().trim().min(1),
    description: z.string().trim().min(1).optional(),
    author: z.string().trim().min(1).optional(),
    authorTitle: z.string().trim().min(1).optional(),
    path: z
      .string()
      .regex(
        /^(?:\/(?:library|notes)\/[a-z0-9]+(?:-[a-z0-9]+)*\/|\/sand-to-thought(?:\/[a-z0-9]+(?:-[a-z0-9]+)*)?\/)$/,
      ),
    collection: z.enum(["library", "sand-to-thought"]).default("library"),
    category: z.enum(["notes", "hardware"]).default("notes"),
    layout: z.enum(["reading", "journey"]).default("reading"),
    status: z.enum(["draft", "published"]),
    publishedAt: date,
    updatedAt: date.optional(),
    image: z
      .string()
      .regex(/^\/(?!\/)[^\s]+$/)
      .default("/brand/png/gradiated-mark-dark-1024.png"),
  })
  .strict()
  .refine(
    (value) => !value.updatedAt || value.updatedAt >= value.publishedAt,
    "updatedAt must not precede publishedAt",
  );

export type ArticleMetadata = z.infer<typeof schema>;
export function parseArticleMetadata(
  source: string,
  file: string,
): ArticleMetadata {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
  if (!match) throw new Error(`${file}: article YAML frontmatter is required`);
  try {
    return schema.parse(parse(match[1]));
  } catch (error) {
    throw new Error(`${file}: invalid article frontmatter`, { cause: error });
  }
}
export function buildArticleRegistry(
  sources: Record<string, string>,
  includeDrafts: boolean,
) {
  const paths = new Set<string>();
  return Object.entries(sources)
    .map(([file, source]) => {
      const article = { ...parseArticleMetadata(source, file), file };
      if (paths.has(article.path))
        throw new Error(`Duplicate article path: ${article.path}`);
      paths.add(article.path);
      return article;
    })
    .filter((article) => includeDrafts || article.status === "published")
    .sort(
      (a, b) =>
        b.publishedAt.localeCompare(a.publishedAt) ||
        a.path.localeCompare(b.path),
    );
}
