# Programmable logic - saved for later

Removed from the opening article on 2026-10-12 with Aidan’s approval. Preserve for the future specialisation/configurable-hardware chapter or a focused article. This is draft source, not current website coverage. Review the wording and technical scope before reusing it.

The matching [animation fragment](programmable-logic-scenes.js) preserves the original drawing, timing, and FPGA signal loop. It belongs inside `SCENES2D.build`, uses its existing drawing helpers, and originally occupied indices 19 and 20. It is not a standalone script. Remap its indices and register the scene keys when integrating it elsewhere.

## Programmable logic

<!-- scene: lut -->

With that in our arsenal, we can zoom back out and make another forest of NANDs, this time packaged into a block called a look-up table, or LUT. Done correctly, you get a black box with three inputs and a single-bit output. Inside, small memory circuits can be programmed to map each of the eight possible inputs (000, 001 and so on) to a 0 or a 1: any arbitrary 3-to-1 function.

> **Visual cue — lut:** Show three inputs selecting among eight stored answer bits.

<!-- scene: fpga -->

Zooming out, we can stack many of these arbitrary function maps side by side. Interconnecting them in a controlled way, with more memory bits, implements any Boolean function. This is the basic description of an FPGA.

> **Visual cue — fpga:** Expand to a grid of LUTs connected by programmable switches.

