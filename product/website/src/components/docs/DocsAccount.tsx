import { CONSOLE_BASE_URL } from "../../urls";

export const DocsAccount = () => (
  <div className="border-b border-line pb-6">
    <a
      className="block w-full border border-ink bg-ink px-3 py-2 text-center text-[11px] text-paper transition-colors hover:bg-transparent hover:text-ink"
      href={CONSOLE_BASE_URL}
    >
      Get API key
    </a>
  </div>
);
