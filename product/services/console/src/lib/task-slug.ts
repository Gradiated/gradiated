const TASK_SLUG_PATTERN = /^[a-z0-9][a-z0-9._-]{0,63}$/;

/** Slugify as the user types: lowercase, spaces → '-', drop anything outside [a-z0-9._-], no leading separators, max 64. */
export const slugifyTaskInput = (value: string) =>
  value
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9._-]/g, "")
    .replace(/^[._-]+/, "")
    .slice(0, 64);

export const isValidTaskSlug = (value: string) => TASK_SLUG_PATTERN.test(value);

export const taskSlugError = (value: string): string | null => {
  if (!value) return "Enter a task name.";
  if (!TASK_SLUG_PATTERN.test(value)) {
    return "Lowercase letters, numbers, '.', '_', '-' only, starting with a letter or number.";
  }
  return null;
};
