export * from "./auth.js";
export * from "./organizations.js";

import * as auth from "./auth.js";
import * as organizations from "./organizations.js";

export const schema = { ...auth, ...organizations };
