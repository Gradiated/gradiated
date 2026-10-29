export type Team = {
  name: string;
  slug: string;
};

export type Person = {
  name: string;
  href?: string;
  photo?: string;
  role?: string;
  teams?: string[];
};

export const teams: Team[] = [];

export const people: Person[] = [
  { name: "James Hawkins", role: "Cofounder and CEO" },
  { name: "Josh Snyder", role: "Cofounder" },
  { name: "Aidan McConnell", role: "Technical staff" },
  { name: "Shmo Gupta", role: "Designer" },
  { name: "Scott Lewis", role: "Executive Assistant" },
];

export const findPerson = (name: string): Person => {
  const person = people.find((candidate) => candidate.name === name);
  if (!person)
    throw new Error(`Unknown person "${name}": add them to src/people.ts.`);

  return person;
};

export const findTeam = (slug: string): Team => {
  const team = teams.find((candidate) => candidate.slug === slug);
  if (!team)
    throw new Error(`Unknown team "${slug}": add it to src/people.ts.`);

  return team;
};

export const teamMembers = (slug: string): Person[] =>
  people.filter((person) => person.teams?.includes(slug));

export const initials = (name: string): string =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
