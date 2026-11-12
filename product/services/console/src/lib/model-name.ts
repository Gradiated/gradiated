export const ORGANIZATION_SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{0,37}[a-z0-9]$/;

export const privateModelName = (
  organizationSlug: string,
  task: string,
  version?: string,
) =>
  version === undefined
    ? `${organizationSlug}/${task}`
    : `${organizationSlug}/${task}/${version}`;

export const organizationSlugError = (value: string): string | null => {
  if (!value) return "Enter a slug.";

  if (!ORGANIZATION_SLUG_PATTERN.test(value)) {
    return "Use 2 to 39 lowercase letters, numbers or hyphens, starting and ending with a letter or number.";
  }

  return null;
};
