import { expect, it } from "vitest";
import {
  buildTeam,
  parseTeamMember,
  placesOf,
  postsIn,
  sectionsOf,
} from "../src/team-metadata";
import { countryCodeOf } from "../src/team-geo";

const profile = (fields: string, body = "") => `---\n${fields}\n---\n${body}`;

const london = "location:\n  city: London\n  country: UK";
const places = { "London, UK": { latitude: 51.5, longitude: -0.12 } };

it("takes the profile's URL from its folder's name", () => {
  const member = parseTeamMember(
    profile("name: Ada Lovelace\nrole: Technical staff", "Hello.\n"),
    "../content/team/ada-lovelace/ada-lovelace.md",
  );

  expect(member.path).toBe("/team/ada-lovelace/");
  expect(member.body).toBe("Hello.");
  expect(member.gallery).toEqual([]);
});

it("names the file when a profile is wrong", () => {
  expect(() =>
    parseTeamMember(
      profile("name: Ada Lovelace"),
      "team/ada-lovelace/ada-lovelace.md",
    ),
  ).toThrow("team/ada-lovelace/ada-lovelace.md: invalid profile front matter");
  expect(() =>
    parseTeamMember(
      profile("name: Ada\nrole: Staff\nnickname: A"),
      "team/ada/ada.md",
    ),
  ).toThrow("team/ada/ada.md");
  expect(() =>
    parseTeamMember(
      profile("name: Ada\nrole: Staff"),
      "team/Ada Lovelace/Ada Lovelace.md",
    ),
  ).toThrow("lowercase with hyphens");
});

it("orders people by `order`, then by name, and skips the template", () => {
  const team = buildTeam({
    "team/_template/your-name.md": profile("name: Your Name\nrole: Your role"),
    "team/zed/zed.md": profile("name: Zed\nrole: Staff"),
    "team/bea/bea.md": profile("name: Bea\nrole: Staff"),
    "team/cy/cy.md": profile("name: Cy\nrole: Staff\norder: 1"),
  });

  expect(team.map((member) => member.name)).toEqual(["Cy", "Bea", "Zed"]);
});

it("wants one Markdown file in a person's folder", () => {
  expect(() =>
    buildTeam({
      "team/ada/ada.md": profile("name: Ada\nrole: Staff"),
      "team/ada/notes.md": profile("name: Ada Too\nrole: Staff"),
    }),
  ).toThrow("one Markdown file");
});

it("refuses two profiles with one name", () => {
  expect(() =>
    buildTeam({
      "team/a/a.md": profile("name: Ada\nrole: Staff"),
      "team/b/b.md": profile("name: Ada\nrole: Staff"),
    }),
  ).toThrow('already "Ada"');
});

it("works out the flag and the pin from the city and country", () => {
  const [ada] = buildTeam(
    { "team/a/a.md": profile(`name: Ada\nrole: Staff\n${london}`) },
    places,
  );

  expect(ada.location).toEqual({
    city: "London",
    country: "UK",
    countryCode: "GB",
    latitude: 51.5,
    longitude: -0.12,
  });
  expect(countryCodeOf("United States")).toBe("US");
  expect(countryCodeOf("india")).toBe("IN");
  expect(countryCodeOf("Côte d’Ivoire")).toBe(countryCodeOf("Cote d’Ivoire"));
  expect(countryCodeOf("Narnia")).toBeUndefined();
});

it("keeps coordinates a profile gives, and wants both or neither", () => {
  const [ada] = buildTeam(
    {
      "team/a/a.md": profile(
        `name: Ada\nrole: Staff\n${london}\n  latitude: 1\n  longitude: 2`,
      ),
    },
    places,
  );

  expect([ada.location?.latitude, ada.location?.longitude]).toEqual([1, 2]);
  expect(() =>
    parseTeamMember(
      profile(`name: Ada\nrole: Staff\n${london}\n  latitude: 1`),
      "team/a/a.md",
    ),
  ).toThrow("team/a/a.md");
});

it("groups people by city and leaves out anyone it cannot place", () => {
  const grouped = placesOf(
    buildTeam(
      {
        "team/a/a.md": profile(`name: Ada\nrole: Staff\n${london}`),
        "team/b/b.md": profile(`name: Bea\nrole: Staff\n${london}`),
        "team/c/c.md": profile("name: Cy\nrole: Staff"),
        "team/d/d.md": profile(
          "name: Dee\nrole: Staff\nlocation:\n  city: Nowhere\n  country: UK",
        ),
      },
      places,
    ),
  );

  expect(grouped).toHaveLength(1);
  expect(grouped[0].key).toBe("London, UK");
  expect(grouped[0].members.map((member) => member.name)).toEqual([
    "Ada",
    "Bea",
  ]);
});

it("turns a profile's headings into its sections", () => {
  const sections = sectionsOf(
    [
      "Hello, I am Ada.",
      "",
      "## Things I've done",
      "- The first program",
      "",
      "```md",
      "## not a heading",
      "```",
      "",
      "## Empty",
      "",
      "## Posts",
      "<!-- a hint for the author,",
      "over two lines -->",
      "",
      "## Bio",
      "Again.",
    ].join("\n"),
  );

  expect(sections.map(({ id, title }) => [id, title])).toEqual([
    ["bio", "Bio"],
    ["things-ive-done", "Things I've done"],
    ["bio-2", "Bio"],
  ]);
  expect(sections[1].markdown).toContain("## not a heading");
});

it("takes the portrait and gallery from the person's images", () => {
  const picture = (name: string) => ({
    height: 10,
    src: `/team/ada/${name}.webp`,
    thumb: `/team/ada/${name}-thumb.webp`,
    width: 10,
  });
  const [ada] = buildTeam(
    {
      "team/ada/ada.md": profile(
        [
          "name: Ada",
          "role: Staff",
          "captions:",
          "  01 Desk.JPG: At the desk.",
        ].join("\n"),
      ),
    },
    {},
    {
      ada: {
        profile: { small: "/team/ada/profile-small.webp", src: "/p.webp" },
        gallery: {
          "01-desk": picture("01-desk"),
          "02-boat": picture("02-boat"),
        },
      },
    },
  );

  expect(ada.photo?.src).toBe("/p.webp");
  expect(ada.gallery.map(({ caption, name }) => [name, caption])).toEqual([
    ["01-desk", "At the desk."],
    ["02-boat", undefined],
  ]);
});

it("keeps the place of a section the page fills in", () => {
  const body = "## Bio\nHi.\n\n## Posts\n\n## Gallery\nPictures.";

  expect(sectionsOf(body).map(({ title }) => title)).toEqual([
    "Bio",
    "Gallery",
  ]);
  expect(sectionsOf(body, ["posts"]).map(({ title }) => title)).toEqual([
    "Bio",
    "Posts",
    "Gallery",
  ]);
});

it("reads the links under Posts as posts, and leaves the rest as text", () => {
  const { posts, rest } = postsIn(
    [
      "Some of my writing.",
      "",
      "- [First](https://example.com/1) — Talk, 2025",
      "- [Second](https://example.com/2)",
      "- Not a link",
    ].join("\n"),
  );

  expect(posts).toEqual([
    { note: "Talk, 2025", title: "First", url: "https://example.com/1" },
    { note: undefined, title: "Second", url: "https://example.com/2" },
  ]);
  expect(rest).toBe("Some of my writing.\n\n- Not a link");
});
