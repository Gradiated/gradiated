import type { StorybookConfig } from "@storybook/react-vite";

const config: StorybookConfig = {
  addons: ["msw-storybook-addon"],
  framework: "@storybook/react-vite",
  stories: ["../src/**/*.stories.tsx"],
  staticDirs: ["../public", "./public"],
  core: { disableTelemetry: true },
  viteFinal: (config) => ({
    ...config,
    define: {
      ...config.define,
      "import.meta.env.VITE_FEATURE_FLAGS": JSON.stringify("training"),
      "import.meta.env.VITE_POSTHOG_KEY": "undefined",
      "import.meta.env.VITE_API_URL": "undefined",
    },
    server: { ...config.server, proxy: undefined },
  }),
};

export default config;
