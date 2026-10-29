// Operations the console calls from a browser session. The public reference
// omits them; the console and website clients are generated with them.
export const consoleOnly = { "x-gradiated-audience": "console" } as const;

export const isConsoleOnly = (operation: unknown): boolean =>
  typeof operation === "object" &&
  operation !== null &&
  "x-gradiated-audience" in operation &&
  operation["x-gradiated-audience"] === consoleOnly["x-gradiated-audience"];
