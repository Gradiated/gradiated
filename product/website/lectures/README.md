# Local lecture presentations

## Lecture 3 — transistor fabrication

A diagram-only presentation of the fabrication article. It keeps the cover artwork, title and left chapter navigation, with enlarged animations. The site navigation, article prose, bibliography and footer are omitted.

From `product/website`, start a local server:

```sh
mise exec -- pnpm exec vite --host 127.0.0.1 --port 5182 --strictPort
```

Open **http://127.0.0.1:5182/lectures/lecture-3/**. If a website Vite server is already running from this checkout, the same path works on its port too.

- Click a chapter in the left contents list to jump to it. On a narrow phone screen, use the chapter picker above the animation.
- Use **← / →** or **Page Up / Page Down** to move between individual steps; the on-screen arrows do the same.
- Use **Replay** to repeat the current animation. The NOT gate retains its input controls.
- The process circle below the contents highlights the current kind of operation. Cleaning and inspection are included as categories but have no separate animated stages; overview scenes highlight none.
- Click the cover artwork to begin. A URL fragment records the current step, so a bookmarked step can be reopened directly.

The saved entry is [lecture-3/index.html](lecture-3/index.html); its React entry and layout are [lecture3.tsx](../../../hardware/publishing/sand-to-thought/lectures/lecture-3/presentation.tsx) and [lecture3.css](../../../hardware/publishing/sand-to-thought/lectures/lecture-3/presentation.css). It reuses the existing fabrication animation and sequence, so future improvements to those drawings also appear here. This is a reusable presentation view, rather than a frozen copy of the article.

This separate HTML entry is served locally by Vite. It is not added to the public site's routes, library or default production build. No server needs to remain running between talks: keep these source files and use the command above to reopen it.

## Lecture 4 — Inside our FPGA

Start the same Vite server as above and open [Lecture 4](http://127.0.0.1:5182/lectures/lecture-4/). Click the cover to begin. Use the left contents, **← / →**, **Page Up / Page Down**, or the on-screen arrows. On a narrow screen, use the contents menu above the slide. **Back to start** returns to the cover. **Replay** restarts the current figure. The URL fragment links to the current slide.

The [HTML entry](lecture-4/index.html) is local, like Lecture 3. The [slide list and entry point](../../../hardware/publishing/sand-to-thought/lectures/lecture-4/presentation.tsx) reuse the FPGA article’s animations. To trim the deck, remove the corresponding keys from its slide list and update the matching sections in the [speaking script](../../../hardware/publishing/sand-to-thought/lectures/lecture-4/script.md). Slide 57 uses an [illustrative cost and throughput chart](../../../hardware/publishing/sand-to-thought/lectures/lecture-4/assets/illustrative-throughput.svg) with four experiments. The final slide sets out the experiment loop and the question it will test.
