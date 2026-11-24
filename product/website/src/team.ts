import media from "./team-media.generated.json";
import places from "./team-places.generated.json";
import { buildTeam, placesOf } from "./team-metadata";

export type { TeamMember, TeamPlace } from "./team-metadata";

export const team = buildTeam(
  import.meta.glob<string>("../content/team/*/*.md", {
    eager: true,
    query: "?raw",
    import: "default",
  }),
  places,
  media,
);

export const teamPlaces = placesOf(team);

export const findMember = (slug: string) =>
  team.find((member) => member.slug === slug);
