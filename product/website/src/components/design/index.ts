/**
 * The Gradiated design system's structural components.
 *
 * Import from here, not from the individual files — the barrel is the public
 * surface; everything not exported from it is an internal detail that may
 * change without notice.
 *
 * The minimal page:
 *
 *   import { Band, Columns, Module, Substrate } from "../components/design";
 *   import "../styles/index.css";
 *
 *   <Substrate>
 *     <Band>
 *       <Module bleed height="viewport" index={0}>…hero…</Module>
 *       <Module index={1} title="Section">
 *         <Columns count={3}>…</Columns>
 *       </Module>
 *     </Band>
 *   </Substrate>
 *
 * See src/styles/README.md for the system's rules and how the pieces fit.
 */

export { Band, Columns, Module } from "./Module";
export { Footer } from "./Footer";
export { HeroBeam } from "./HeroBeam";
export { HeroBeamRaw } from "./HeroBeamRaw";
export { HomeFlow } from "./HomeFlow";
export { FooterBar } from "./FooterBar";
export { Arrow, ContentsIcon, GridIcon, ListIcon } from "./icons";
export { ChipStack } from "./ChipStack";
export { Benchmark } from "./Benchmark";
export { CodeBlock } from "./CodeBlock";
export { CostStory } from "./CostStory";
export { StoryCard, StoryList, StoryRow } from "./Story";
export type { Story, StoryCover, StoryArt } from "./Story";
export { Logo } from "./Logo";
export { Nav } from "./Nav";
export { Reading } from "./Reading";
export { Reveal } from "./Reveal";
export { SectionFab } from "./SectionFab";
export { WordmarkField } from "./WordmarkField";
export { WaferArtwork } from "./WaferArtwork";
export type { WaferArtworkOptions } from "./WaferArtwork";
export { ThemeGallery } from "./ThemeGallery";
export { RadiusSwitcher } from "./RadiusSwitcher";
export { Tabs } from "./Tabs";
export { WaveField } from "./WaveField";
export { Part, Spec, Storybook } from "./Storybook";
export type { Group, Section } from "./Storybook";
export {
  Cards,
  Features,
  Fold,
  Marquee,
  PageHero,
  Showpiece,
} from "./Sections";
export type { CardItem } from "./Sections";
export { StoryReel } from "./StoryReel";
export type { Chapter } from "./StoryReel";
export { TierExplorer } from "./TierExplorer";
export { Substrate } from "./Substrate";
