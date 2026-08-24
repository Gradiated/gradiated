import type { CSSProperties, ReactNode } from 'react';

export type Note = {
  slug: string;
  date: string;
  title: string;
  description: string;
};

export const notes = [
  {
    slug: 'working-with-us',
    date: '2026-07-15',
    title: 'Working with us',
    description: 'We are hiring founding engineers.',
  },
  {
    slug: 'our-thesis',
    date: '2026-07-13',
    title: 'Thesis',
    description: 'Inference should be a choice, not a constraint.',
  },
] satisfies Note[];

export const ThesisContent = (): ReactNode => (
    <>
      <p>
        AI is moving from software that responds to people, to software that keeps working when nobody is there. As models get smarter and more applications connect them to real-world work, the world is going to have a near-insatiable demand for inference.
      </p>
      <p>
        Intelligence is comparable to the invention of electricity. Factories initially replaced steam engines with electric motors to carry out the same work at reduced cost. But once electricity became cheap enough, it reorganized industry: refrigeration, elevators, radios, air conditioning, and home appliances followed. Demand for power rose enormously. We think there will be near-unlimited demand for inference—likely on a far more dramatic scale, because of what AI can unlock. AI is still at the start of this journey. In coding, for example, models mostly emulate a human developer and generate lots of iterative pull requests. The overall design of software products has not changed entirely, <em>yet</em>.
      </p>
      <p>
        The first part of that transformation is longer-running work moving to the cloud. Software is starting to shift from reactive to proactive: agents can research, plan, use tools, and keep working for hours without a human waiting for each response.
      </p>
      <p>
        Inference today is not built for those cloud tasks. They can run for hours without human interaction and tolerate much higher latency. For them, <em>efficiency</em> is the priority, not <em>latency</em>. Current inference is poorly set up for this. Ask any developer and they will tell you that everything is heading in this direction.
      </p>
      <p>
        Gradiated is a harness for this kind of work, with an API underneath. Developers give the harness a task, tools, a budget, a deadline, and a quality bar. It plans, runs, and revises the work; the API lets them control the cost and latency tradeoffs beneath it. The goal is simple: use the right model, at the right cost, for each part of the job.
      </p>
      <p>
        Our approach is to optimize every layer of the vertical stack. The product is a developer tool—not infrastructure for its own sake, in the same way Stripe is a developer tool rather than a fintech company. Underneath are the software, infrastructure, and eventually chip design needed to make those runs cheaper and more capable. As with any engineering task, optimizing across the whole stack is how to win. Gradiated will go much deeper from the start.
      </p>
      <h2>Inference systems and hardware</h2>
      <p>
        We&apos;ve already made significant progress in inference systems research. Take GLM 5.2 as an example. Today, inference is fundamentally memory-bandwidth bound rather than compute-bound. In practice, only around 3% of the model&apos;s parameters are responsible for roughly 70% of the computation during inference. That changes how you should think about hardware design. Rather than building a general-purpose accelerator, you can architect a chip specifically for this workload—for example, pairing around 20GB of ultra-high-bandwidth memory dedicated to the hot working set used in matrix multiplication with approximately 380GB of lower-cost memory for the remaining parameters. By matching the memory hierarchy to the model&apos;s access patterns, you dramatically reduce bandwidth bottlenecks while substantially lowering the cost of inference.
      </p>
      <p>
        The optimal architecture changes as models evolve. A dense model like GLM 5.2 has very different requirements from a sparse mixture-of-experts model such as Kimi K2, where only a subset of experts are active on each forward pass. Those models benefit from different memory layouts, routing mechanisms, interconnect topologies, and scheduling strategies. There is unlikely to be a single &quot;best&quot; accelerator for every frontier model.
      </p>
      <p>
        This is why we&apos;re building a full end-to-end simulation environment spanning both hardware and software. Instead of designing chips or software in isolation, we can co-design compilers, runtimes, memory hierarchies, and silicon around the model architectures we serve. The simulator lets us explore architectural trade-offs before tape-out, optimize across the entire stack, and rapidly adapt as new model architectures emerge. Rather than chasing yesterday&apos;s workloads, we&apos;re designing inference infrastructure that evolves alongside the models themselves.
      </p>
      <p>
        There will be challenges. Chip design is slow and the supply chain is difficult. Software alone is enough to win right now, but getting the full stack right is key to building a trillion-dollar company—at which point we are directly competing with Nvidia.
      </p>
      <p>
        If Gradiated succeeds, exactly the right intelligence will be provided for every task. That will make us the leading provider, because it means we outperform every provider.
      </p>
      <p>So the plan is:</p>
      <ul>
        <li>Ship cheaper inference for cloud tasks with lower latency needs. Use software to achieve this while making margin in the early days.</li>
        <li>Build chips at scale to provide more inference flexibility than anyone else can provide.</li>
        <li>As we build expertise and distribution, expand into all of inference.</li>
      </ul>
    </>
);

export const WorkingWithUsContent = (): ReactNode => (
    <>
      <p>We are hiring founding engineers.</p>
      <p>We are looking for people who either have experience building chips, or have experience building looping agentic research systems.</p>
      <p>We are very early. This is the time for maximum upside.</p>
      <p>We want people who are extraordinarily anti-bureaucratic, optimistic, and high-agency.</p>
    </>
);

export const ValuesContent = (): ReactNode => (
    <>
      <section><h2>Depth</h2><p>Question every assumption, through every layer—from software to hardware and silicon.</p></section>
      <section><h2>Meritocracy</h2><p>The best ideas win. Some people will contribute more and benefit more. That is good.</p></section>
    </>
);

export const BrandContent = (): ReactNode => (
    <>
      <p className="handbook-lead">Everything is considered.</p>
      <p>Socrates tested claims by questioning their assumptions. We apply the same standard to the brand. Every word, line, colour, and interaction should have a reason to exist.</p>
      <section>
        <h2>Principles</h2>
        <div className="brand-principles">
          <div><h3>Begin with the claim</h3><p>Lead with the thing that is true or useful. Context follows. Do not hide a precise idea behind scene-setting or slogans.</p></div>
          <div><h3>Go down the stack</h3><p>Show the reasoning beneath the result. The visual system should suggest depth, construction, revision, and relationships between layers.</p></div>
          <div><h3>Remove what cannot answer for itself</h3><p>Decoration needs a purpose. If a word, rule, image, or interaction does not improve meaning or orientation, remove it.</p></div>
          <div><h3>Prefer evidence to assertion</h3><p>Specifics are more persuasive than superlatives. Use examples, constraints, measurements, and trade-offs wherever possible.</p></div>
        </div>
      </section>
      <section>
        <h2>Colour</h2>
        <p>The palette refers to the setting of Plato&apos;s Academy without attempting to recreate antiquity. The school stood beside a sacred olive grove and its surviving site is marked by dry earth, pale limestone, paths, and fragments—not monumental white marble. The result is deliberately limited: stone, ink, olive, and earth.</p>
        <dl className="brand-palette">
          <PaletteItem swatch="#e8e2d5" name="Academy stone" code="#E8E2D5">The principal light ground. Its warmth refers to limestone and sunlit earth, while retaining the quiet character of uncoated paper.</PaletteItem>
          <PaletteItem swatch="#1c1b18" name="Carbon ink" code="#1C1B18">The principal text colour and dark ground. Near-black is easier on the eye than absolute black and ties the visual system to writing and argument.</PaletteItem>
          <PaletteItem swatch="#72745a" name="Weathered olive" code="#72745A">The principal interaction colour, drawn from the olive grove in which the Academy was set. Use it for links, controls, and active states—not decoration.</PaletteItem>
          <PaletteItem swatch="#9a7449" name="Attic earth" code="#9A7449">A restrained expressive colour drawn from the dry, ochre ground of the Academy site. Use it for diagrams, circuit nodes, numeric output, and selected text.</PaletteItem>
          <PaletteItem swatch="#f0ece2" name="Pale limestone" code="#F0ECE2">The principal light colour in dark mode. It carries the warmth of the stone ground rather than introducing a clinical white.</PaletteItem>
          <PaletteItem swatch="#c9c1b2" name="Cut stone" code="#C9C1B2">Rules, borders, and inactive controls. It separates information without competing with it.</PaletteItem>
        </dl>
        <p className="palette-note">In dark mode, olive is raised to <code>#A6A887</code>, earth to <code>#C09A68</code>, and cut stone deepens to <code>#49463E</code> to preserve contrast. Supporting surfaces and muted text are derived from the same stone and ink tones.</p>
      </section>
      <section><h2>Use</h2><p>Colour should communicate state, hierarchy, or interaction. Olive indicates interaction; earth adds emphasis to diagrams and output. Neither should become decoration. Error colours may depart from the palette where convention requires it, but they are functional rather than expressive.</p></section>
      <section><h2>Typography</h2><p>Newsreader carries propositions, titles, and moments that need reflection. Libre Franklin carries explanation, navigation, labels, and interfaces. Large type may be quiet; small type must be exact. Avoid unnecessary weights, ornamental italics, and artificial hierarchy.</p></section>
      <section><h2>Voice</h2><p>Write plainly, specifically, and with intellectual confidence. Ask a question only when the product or the next sentence can help answer it. Avoid grand claims, vague philosophy, inflated metaphors, and language that sounds profound without saying anything.</p></section>
      <section><h2>Artwork</h2><p>Artwork draws from the Academy as a place of inquiry, not from mythology. Use architecture, human scale, measured construction, worn fresco, vellum, stone, carbon, and evidence of revision. Figures are ordinary thinkers, never gods or heroes. Colour remains mineral and sparse: stone and ink first, olive and earth second.</p></section>
      <section><h2>Interaction</h2><p>Motion should reveal structure or state. Circuit paths expose the system beneath the surface; hover treatments clarify what can be opened; the theme switch records a considered choice. Interactions should never exist solely to demonstrate cleverness.</p></section>
    </>
);

type PaletteItemProps = {
  swatch: string;
  name: string;
  code: string;
  children: ReactNode;
};

const PaletteItem = ({ swatch, name, code, children }: PaletteItemProps): ReactNode => (
    <div>
      <dt><i style={{ '--swatch': swatch } as CSSProperties} /><span>{name} <code>{code}</code></span></dt>
      <dd>{children}</dd>
    </div>
);

export const PrivacyContent = (): ReactNode => (
    <>
      <p>Effective date: July 13, 2026</p>
      <p>Gradiated, Inc. (“Gradiated,” “we,” “us,” or “our”) respects your privacy. This policy explains how we collect, use, and share information when you visit gradiated.com or contact us.</p>
      <h2>Information we collect</h2>
      <p>We may collect information you provide directly, including your name, email address, company, and the contents of messages or waitlist requests. We may also collect limited technical information such as browser type, device information, IP address, and pages visited through standard web logs.</p>
      <h2>How we use information</h2>
      <p>We use information to respond to enquiries, operate and improve our website and services, communicate about Gradiated, protect our systems, and comply with legal obligations. We do not sell personal information.</p>
      <h2>How we share information</h2>
      <p>We may share information with service providers that support our website and business operations, when required by law, or in connection with a corporate transaction. We require providers to handle information only as needed to provide their services.</p>
      <h2>Your choices</h2>
      <p>You may request access to, correction of, or deletion of personal information we hold about you, subject to applicable law. You may opt out of marketing communications at any time. To make a request, email signal@gradiated.com.</p>
      <h2>Changes and contact</h2>
      <p>We may update this policy from time to time and will post the revised version here. Questions about this policy can be sent to signal@gradiated.com.</p>
    </>
);
