import { DocsInlineCode } from "../docs/DocsCodeBlock";
import { Callout } from "./Callout";
import { CountriesWeHireIn } from "./CountriesWeHireIn";
import { MethodCodeBlock } from "./MethodCodeBlock";
import { Person, Team } from "./Person";
import { PrivateLink } from "./PrivateLink";

export { Callout, CountriesWeHireIn, Person, PrivateLink, Team };

export const methodComponents = {
  Callout,
  CountriesWeHireIn,
  Person,
  PrivateLink,
  Team,
  code: DocsInlineCode,
  pre: MethodCodeBlock,
};
