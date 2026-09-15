export * from "./auth.js";
export * from "./instances.js";
export * from "./organizations.js";
export * from "./waitlist.js";

import * as auth from "./auth.js";
import * as instances from "./instances.js";
import * as organizations from "./organizations.js";
import * as waitlist from "./waitlist.js";

export const schema = { ...auth, ...organizations, ...instances, ...waitlist };
