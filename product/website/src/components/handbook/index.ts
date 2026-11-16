import { DocsInlineCode } from "../docs/DocsCodeBlock";
import { Callout } from "./Callout";
import { CompensationCalculator } from "./CompensationCalculator";
import { CountriesWeHireIn } from "./CountriesWeHireIn";
import { HandbookCodeBlock } from "./HandbookCodeBlock";
import { H2, H3, H4 } from "./HeadingLink";
import { Person, Team } from "./Person";
import { PrivateLink } from "./PrivateLink";

export {
  Callout,
  CompensationCalculator,
  CountriesWeHireIn,
  Person,
  PrivateLink,
  Team,
};

export const handbookComponents = {
  Callout,
  CompensationCalculator,
  CountriesWeHireIn,
  Person,
  PrivateLink,
  Team,
  code: DocsInlineCode,
  h2: H2,
  h3: H3,
  h4: H4,
  pre: HandbookCodeBlock,
};
