import type { AgentIntegration } from "../agent.js";
import {
  addWrapperToPath,
  hasWrapperOnPath,
  pathNextStep,
  removeWrapperFromPath,
} from "./shell-path.js";
import {
  installWrapper,
  isWrapperInstalled,
  uninstallWrapper,
  wrapperCommand,
} from "./wrapper.js";

const USAGE_NOTES = [
  "your normal `claude` is unchanged; /model <id> switches models in a session",
  "ANTHROPIC_MODEL=<id> claude-gradiated overrides the model for one run",
  "Claude Pro/Max login does not work through a custom gateway; claude-gradiated is for Anthropic API-key setups",
];

export const claude: AgentIntegration = {
  name: "claude",
  label: "Claude Code",
  uninstallHint: "claude-gradiated command and PATH entry",
  runsWithoutClient: true,
  isConfigured: async (paths) =>
    isWrapperInstalled(paths) || (await hasWrapperOnPath(paths)),
  preview: (_setup, paths) => [
    {
      title: "Claude Code wrapper",
      body: `Would write ${wrapperCommand(paths)} and add it to PATH`,
    },
  ],
  install: async (setup, paths) => {
    const wrapperChanged = await installWrapper(paths, {
      apiBaseUrl: setup.apiBaseUrl,
      modelId: setup.model.id,
    });
    const updatedProfiles = await addWrapperToPath(paths);
    const pathStep = pathNextStep(
      updatedProfiles,
      await hasWrapperOnPath(paths),
    );

    return {
      changes: [
        ...(wrapperChanged
          ? [`claude-gradiated wrapper in ${wrapperCommand(paths)}`]
          : []),
        ...updatedProfiles.map((profile) => `PATH entry in ${profile.path}`),
      ],
      nextStep: {
        action: pathStep.action,
        notes: [...pathStep.notes, ...USAGE_NOTES],
      },
    };
  },
  uninstall: async (paths) => {
    const wrapperRemoved = await uninstallWrapper(paths);
    const updatedProfiles = await removeWrapperFromPath(paths);

    return {
      removed: [
        ...(wrapperRemoved
          ? [`claude-gradiated wrapper (${wrapperCommand(paths)})`]
          : []),
        ...updatedProfiles.map((profile) => `PATH entry (${profile.path})`),
      ],
      backedUp: false,
    };
  },
};
