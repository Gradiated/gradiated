import { DocsInlineCode } from "../docs/DocsCodeBlock";
import { Callout } from "./Callout";
import { CountriesWeHireIn } from "./CountriesWeHireIn";
import { HandbookCodeBlock } from "./HandbookCodeBlock";
import { Person, Team } from "./Person";
import { PrivateLink } from "./PrivateLink";

export { Callout, CountriesWeHireIn, Person, PrivateLink, Team };

export const handbookComponents = {
  Callout,
  CountriesWeHireIn,
  Person,
  PrivateLink,
  Team,
  code: DocsInlineCode,
  pre: HandbookCodeBlock,
};
