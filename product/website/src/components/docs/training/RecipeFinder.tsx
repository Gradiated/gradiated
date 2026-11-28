import { useId, useState } from "react";
import type { KeyboardEvent, ReactElement } from "react";
import { Link } from "react-router-dom";

import { useDocsLanguage, useSdkLanguage } from "../DocsLanguage";
import { CodeSample } from "./CodeSample";
import { SDK_LANGUAGES, catalogModel, defaultModelFor, usd } from "./data";
import type { RecipeKind } from "./data";
import { RECIPES, recipeSnippet } from "./recipes";

type Choice = { id: string; label: string; to: RecipeKind | "teach" };

const GOALS: Choice[] = [
  { id: "cost", label: "Spend less on calls to a big model", to: "router" },
  { id: "teach", label: "Teach a model a task, format or style", to: "teach" },
  {
    id: "decide",
    label: "Make a fixed-choice decision about an input",
    to: "decision",
  },
  {
    id: "context",
    label: "Stop resending a long prompt or document",
    to: "cartridge",
  },
  {
    id: "search",
    label: "Get better search results over my documents",
    to: "embedding",
  },
  { id: "grade", label: "Score answers without calling a judge", to: "reward" },
];

const DATA: Choice[] = [
  { id: "examples", label: "Examples of good outputs", to: "sft" },
  {
    id: "pairs",
    label: "Pairs of a preferred and a rejected answer",
    to: "dpo",
  },
  {
    id: "prompts",
    label: "Only prompts, and a bigger model that answers them well",
    to: "distill",
  },
];

const ChoiceGroup = ({
  label,
  choices,
  value,
  onChange,
}: {
  label: string;
  choices: Choice[];
  value: string;
  onChange: (id: string) => void;
}): ReactElement => {
  const id = useId();

  const onKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    const step =
      event.key === "ArrowDown" || event.key === "ArrowRight"
        ? 1
        : event.key === "ArrowUp" || event.key === "ArrowLeft"
          ? -1
          : 0;
    if (!step) return;

    event.preventDefault();
    const next = choices[(index + step + choices.length) % choices.length];
    onChange(next.id);
    const group = event.currentTarget.parentElement;
    (
      group?.children[choices.indexOf(next)] as HTMLElement | undefined
    )?.focus();
  };

  return (
    <div className="gr-dx-question">
      <p className="gr-dx-question-label" id={id}>
        {label}
      </p>
      <div aria-labelledby={id} className="gr-dx-choices" role="radiogroup">
        {choices.map((choice, index) => (
          <button
            aria-checked={choice.id === value}
            className="gr-dx-choice"
            key={choice.id}
            onClick={() => onChange(choice.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            role="radio"
            tabIndex={choice.id === value ? 0 : -1}
            type="button"
          >
            {choice.label}
          </button>
        ))}
      </div>
    </div>
  );
};

export const RecipeFinder = (): ReactElement => {
  const [goal, setGoal] = useState("teach");
  const [data, setData] = useState("examples");
  const language = useSdkLanguage();
  const { setLanguage } = useDocsLanguage();

  const goalChoice = GOALS.find((choice) => choice.id === goal) ?? GOALS[1];
  const kind: RecipeKind =
    goalChoice.to === "teach"
      ? ((DATA.find((choice) => choice.id === data) ?? DATA[0])
          .to as RecipeKind)
      : goalChoice.to;
  const recipe = RECIPES[kind];
  const model = recipe.model
    ? catalogModel(recipe.model)
    : defaultModelFor(kind);
  const sample = recipeSnippet(kind, language);

  return (
    <section aria-label="Find a recipe" className="gr-dx gr-dx-finder">
      <div className="gr-dx-finder-questions">
        <ChoiceGroup
          choices={GOALS}
          label="1. What do you want to change?"
          onChange={setGoal}
          value={goal}
        />
        {goalChoice.to === "teach" ? (
          <ChoiceGroup
            choices={DATA}
            label="2. What data do you have?"
            onChange={setData}
            value={data}
          />
        ) : null}
      </div>

      <div aria-live="polite" className="gr-dx-finder-result">
        <p className="gr-dx-kicker">Use</p>
        <h3 className="gr-dx-finder-recipe">
          <code>{recipe.className}</code>
        </h3>
        <p className="gr-dx-finder-why">{recipe.why}</p>

        <dl className="gr-dx-facts">
          <div>
            <dt>Base model</dt>
            <dd>
              <code>{model.id}</code>
              {recipe.model ? null : " (chosen by the recipe)"}
            </dd>
          </div>
          <div>
            <dt>Catalog rate</dt>
            <dd>{usd(model.price)} per 1M training tokens</dd>
          </div>
        </dl>

        <p className="gr-dx-small-label">One record</p>
        <pre className="gr-dx-record" tabIndex={0}>
          <code>{recipe.record}</code>
        </pre>

        <div className="gr-dx-finder-code">
          <div
            aria-label="SDK language"
            className="gr-doc-tablist gr-dx-langtabs"
            role="tablist"
          >
            {SDK_LANGUAGES.map((option) => (
              <button
                aria-selected={option === language}
                className="gr-doc-tab"
                key={option}
                onClick={(event) => setLanguage(option, event.currentTarget)}
                role="tab"
                type="button"
              >
                {option}
              </button>
            ))}
          </div>
          <CodeSample code={sample.code} lang={sample.lang} />
        </div>

        <Link className="gr-dx-more" to={recipe.href}>
          {recipe.title}: read the guide
        </Link>
      </div>
    </section>
  );
};

export default RecipeFinder;
