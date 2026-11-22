# Sand to Thought publishing

Follow hardware/AGENTS.md and the shared style guide. These are the canonical article, figure and lecture sources. The website imports them. Editorial plans and learning notes must not be included as public prose. Preserve authored wording and dated history. Keep evidence types and illustrative graphics explicit. Update the FPGA article plan when a reusable teaching figure changes, and link engineering claims to the inference records.

## FPGA article: sole editing and publication source

Aidan confirmed on 19 November 2026 that the reconciled article with all thirteen inference experiments is the only FPGA article version intended for publication. On this Mac, its sole working checkout is `/Users/aidanmcconnell/dev/gradiated`, currently on `FPGA-deep-dive`.

- Edit its `hardware/publishing/sand-to-thought/articles/fpga/script.md`, figures, references, results selection and plan in that checkout. The website entry point is `product/website/content/articles/fpga.mdx` in the same checkout.
- The local preview is `http://127.0.0.1:5173/sand-to-thought/fpga/`. Before an FPGA edit, verify the absolute checkout path and, for preview work, the checkout serving the preview. A matching relative path in another Git worktree does not make it the working source.
- The FPGA copy in `/Users/aidanmcconnell/dev/gradiated-hardware-wip` is superseded and retained for recovery only. Do not edit, synchronise, preview or publish that article copy. Continue FPGA publishing work in the canonical checkout, even if this instruction was read in another worktree. Separate inference research may continue in its authorised checkout.
- Preserve Aidan's direct editor changes by reading the current canonical files before each edit. Do not create a second working draft or overwrite them with an older copy. Future publication must use the reconciled canonical source. Publication still requires Aidan's authorisation.
