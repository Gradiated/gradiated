# Hardware publishing

Canonical article prose, references, figures, lecture scripts and presentation source live under `sand-to-thought/`. The website imports these sources. Route metadata and thin presentation entry points remain in `product/website`, alongside shared design components and public URL assets.

Run the website from the repository’s `product/website` directory using its existing Vite command. Article and lecture URLs are unchanged. TypeScript includes this directory and resolves its libraries through the website’s dependencies. Vite uses the same dependency instances, Tailwind scans the source, and the website’s Turbo build includes it in the cache inputs. A website build requires the repository checkout including `hardware`, not a copied `product` directory alone.

Publishing is source within the repository, not a separate pnpm workspace outside `product/`. Add library dependencies to `product/website/package.json`. For new external imports here, update the website’s TypeScript paths and Vite/Vitest dependency resolution as needed. The product lockfile remains the single dependency lock.

## Publishing research results

Each article may include `results.json`, validated against `hardware/research/inference/schemas/publication.schema.json`, containing a schema version, publication ID and explicit selected run references, including their hashes. Freeze the selection for a published revision. Later runs must not silently change a published chart. Lecture charts can use the same selection.

For every measured chart, identify its metric and unit, boundary, comparison protocol, data selection and calculation version. Preserve raw observations. Keep illustrative graphics explicitly labelled. Placeholder shapes are not benchmark results.

Before publication, validate records, quality gates, compatibility, repeated measurements and artifact availability. Explain methods and limitations, and select public supporting data deliberately. Internal absolute paths, credentials and private logs are not public datasets. External citations support architectural explanations; our selected measurements support our empirical claims.

The current FPGA publication manifest contains no measured runs. Its opening and lecture performance charts remain illustrative, and the closing experiments remain planned.
