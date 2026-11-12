// The shapes every part of the radar shares. No imports, so it runs as-is
// under Node's built-in type stripping.

export type SourceName = "Hugging Face" | "OpenRouter";

/** One model as a source lists it. */
export type Model = {
  /** The source's own ID, e.g. "moonshotai/Kimi-K3.1-Pro". */
  id: string;
  /** The Hugging Face org or OpenRouter prefix it was listed under. */
  owner: string;
  /** What people call it, e.g. "MoonshotAI: Kimi K3.1 Pro". */
  name: string;
  url: string;
  /** Short facts for the alert, e.g. "weights live". */
  details: string[];
  /** The Hugging Face model holding its weights, when the source names one. */
  weights?: string;
};

/** Everything a source lists under one org or prefix. */
export type Scan = {
  /** Key for the seen-IDs store, e.g. "huggingface:moonshotai". */
  scope: string;
  owner: string;
  models: Model[];
};

/** A source of models: Hugging Face or OpenRouter. */
export interface Source {
  readonly name: SourceName;
  /** Lists the models under each owner it was given, one scan per owner. */
  scan(): Promise<Scan[]>;
  /**
   * Adds facts that cost a request per model. The radar calls it only for new
   * models, just before alerting.
   */
  describe?(models: Model[]): Promise<Model[]>;
}

/** New models from one lab on one source, sent as one message. */
export type Alert = {
  source: SourceName;
  lab: string;
  models: Model[];
};

/** Somewhere alerts go: Slack, the console, or a future channel. */
export interface Notifier {
  send(alerts: Alert[]): Promise<void>;
}
