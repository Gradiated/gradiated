import { team } from "./team";

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

/* Derived from the profiles in content/team/, so a person is added in one
   place and the handbook's name pills link to their profile. */
export const people: Person[] = team.map((member) => ({
  name: member.name,
  href: member.path,
  photo: member.photo?.small,
  role: member.role,
}));

export const findPerson = (name: string): Person => {
  const person = people.find((candidate) => candidate.name === name);
  if (!person)
    throw new Error(
      `Unknown person "${name}": add a profile for them in content/team/.`,
    );

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
