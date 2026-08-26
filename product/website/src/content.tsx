import type { CSSProperties, ReactNode } from "react";
import { SiteLink } from "./components/SiteLink";

export type Note = {
  slug: string;
  date: string;
  title: string;
  description: string;
};

export const notes = [
  {
    slug: "working-with-us",
    date: "2026-07-15",
    title: "Working with us",
    description: "We are hiring founding engineers.",
  },
  {
    slug: "our-thesis",
    date: "2026-07-13",
    title: "Thesis",
    description: "Inference should be a choice, not a constraint.",
  },
] satisfies Note[];

export const ThesisContent = (): ReactNode => (
  <>
    <p>
      AI is moving from software that responds to people, to software that keeps
      working when nobody is there. As models get smarter and more applications
      connect them to real-world work, the world is going to have a
      near-insatiable demand for inference.
    </p>
    <p>
      Intelligence is comparable to the invention of electricity. Factories
      initially replaced steam engines with electric motors to carry out the
      same work at reduced cost. But once electricity became cheap enough, it
      reorganized industry: refrigeration, elevators, radios, air conditioning,
      and home appliances followed. Demand for power rose enormously. We think
      there will be near-unlimited demand for inference—likely on a far more
      dramatic scale, because of what AI can unlock. AI is still at the start of
      this journey. In coding, for example, models mostly emulate a human
      developer and generate lots of iterative pull requests. The overall design
      of software products has not changed entirely, <em>yet</em>.
    </p>
    <p>
      The first part of that transformation is longer-running work moving to the
      cloud. Software is starting to shift from reactive to proactive: agents
      can research, plan, use tools, and keep working for hours without a human
      waiting for each response.
    </p>
    <p>
      Inference today is not built for those cloud tasks. They can run for hours
      without human interaction and tolerate much higher latency. For them,{" "}
      <em>efficiency</em> is the priority, not <em>latency</em>. Current
      inference is poorly set up for this. Ask any developer and they will tell
      you that everything is heading in this direction.
    </p>
    <p>
      Gradiated is a harness for this kind of work, with an API underneath.
      Developers give the harness a task, tools, a budget, a deadline, and a
      quality bar. It plans, runs, and revises the work; the API lets them
      control the cost and latency tradeoffs beneath it. The goal is simple: use
      the right model, at the right cost, for each part of the job.
    </p>
    <p>
      Our approach is to optimize every layer of the vertical stack. The product
      is a developer tool—not infrastructure for its own sake, in the same way
      Stripe is a developer tool rather than a fintech company. Underneath are
      the software, infrastructure, and eventually chip design needed to make
      those runs cheaper and more capable. As with any engineering task,
      optimizing across the whole stack is how to win. Gradiated will go much
      deeper from the start.
    </p>
    <h2>Inference systems and hardware</h2>
    <p>
      We&apos;ve already made significant progress in inference systems
      research. Take GLM 5.2 as an example. Today, inference is fundamentally
      memory-bandwidth bound rather than compute-bound. In practice, only around
      3% of the model&apos;s parameters are responsible for roughly 70% of the
      computation during inference. That changes how you should think about
      hardware design. Rather than building a general-purpose accelerator, you
      can architect a chip specifically for this workload—for example, pairing
      around 20GB of ultra-high-bandwidth memory dedicated to the hot working
      set used in matrix multiplication with approximately 380GB of lower-cost
      memory for the remaining parameters. By matching the memory hierarchy to
      the model&apos;s access patterns, you dramatically reduce bandwidth
      bottlenecks while substantially lowering the cost of inference.
    </p>
    <p>
      The optimal architecture changes as models evolve. A dense model like GLM
      5.2 has very different requirements from a sparse mixture-of-experts model
      such as Kimi K3, where only a subset of experts are active on each forward
      pass. Those models benefit from different memory layouts, routing
      mechanisms, interconnect topologies, and scheduling strategies. There is
      unlikely to be a single &quot;best&quot; accelerator for every frontier
      model.
    </p>
    <p>
      This is why we&apos;re building a full end-to-end simulation environment
      spanning both hardware and software. Instead of designing chips or
      software in isolation, we can co-design compilers, runtimes, memory
      hierarchies, and silicon around the model architectures we serve. The
      simulator lets us explore architectural trade-offs before tape-out,
      optimize across the entire stack, and rapidly adapt as new model
      architectures emerge. Rather than chasing yesterday&apos;s workloads,
      we&apos;re designing inference infrastructure that evolves alongside the
      models themselves.
    </p>
    <p>
      There will be challenges. Chip design is slow and the supply chain is
      difficult. Software alone is enough to win right now, but getting the full
      stack right is key to building a trillion-dollar company—at which point we
      are directly competing with Nvidia.
    </p>
    <p>
      If Gradiated succeeds, exactly the right intelligence will be provided for
      every task. That will make us the leading provider, because it means we
      outperform every provider.
    </p>
    <p>So the plan is:</p>
    <ul>
      <li>
        Ship cheaper inference for cloud tasks with lower latency needs. Use
        software to achieve this while making margin in the early days.
      </li>
      <li>
        Build chips at scale to provide more inference flexibility than anyone
        else can provide.
      </li>
      <li>
        As we build expertise and distribution, expand into all of inference.
      </li>
    </ul>
  </>
);

export const WorkingWithUsContent = (): ReactNode => (
  <>
    <p>We are hiring founding engineers.</p>
    <p>
      We are looking for people who either have experience building chips, or
      have experience building looping agentic research systems.
    </p>
    <p>We are very early. This is the time for maximum upside.</p>
    <p>
      We want people who are extraordinarily anti-bureaucratic, optimistic, and
      high-agency.
    </p>
  </>
);

export const ValuesContent = (): ReactNode => (
  <>
    <section>
      <h2>Depth</h2>
      <p>
        Question every assumption, through every layer—from software to hardware
        and silicon.
      </p>
    </section>
    <section>
      <h2>Meritocracy</h2>
      <p>
        The best ideas win. Some people will contribute more and benefit more.
        That is good.
      </p>
    </section>
  </>
);

export const BrandContent = (): ReactNode => (
  <>
    <p className="handbook-lead">Everything is considered.</p>
    <p>
      Socrates tested claims by questioning their assumptions. We apply the same
      standard to the brand. Every word, line, color, and interaction should
      have a reason to exist.
    </p>
    <section>
      <h2>Principles</h2>
      <div className="brand-principles">
        <div>
          <h3>Begin with the claim</h3>
          <p>
            Lead with the thing that is true or useful. Context follows. Do not
            hide a precise idea behind scene-setting or slogans.
          </p>
        </div>
        <div>
          <h3>Go down the stack</h3>
          <p>
            Show the reasoning beneath the result. The visual system should
            suggest depth, construction, revision, and relationships between
            layers.
          </p>
        </div>
        <div>
          <h3>Remove what cannot answer for itself</h3>
          <p>
            Decoration needs a purpose. If a word, rule, image, or interaction
            does not improve meaning or orientation, remove it.
          </p>
        </div>
        <div>
          <h3>Prefer evidence to assertion</h3>
          <p>
            Specifics are more persuasive than superlatives. Use examples,
            constraints, measurements, and trade-offs wherever possible.
          </p>
        </div>
      </div>
    </section>
    <section>
      <h2>Color</h2>
      <p>
        The palette refers to the setting of Plato&apos;s Academy without
        attempting to recreate antiquity. The school stood beside a sacred olive
        grove and its surviving site is marked by dry earth, pale limestone,
        paths, and fragments—not monumental white marble. The result is
        deliberately limited: stone, ink, olive, and earth.
      </p>
      <dl className="brand-palette">
        <PaletteItem swatch="#e8e2d5" name="Academy stone" code="#E8E2D5">
          The principal light ground. Its warmth refers to limestone and sunlit
          earth, while retaining the quiet character of uncoated paper.
        </PaletteItem>
        <PaletteItem swatch="#1c1b18" name="Carbon ink" code="#1C1B18">
          The principal text color and dark ground. Near-black is easier on the
          eye than absolute black and ties the visual system to writing and
          argument.
        </PaletteItem>
        <PaletteItem swatch="#72745a" name="Weathered olive" code="#72745A">
          The principal interaction color, drawn from the olive grove in which
          the Academy was set. Use it for links, controls, and active states—not
          decoration.
        </PaletteItem>
        <PaletteItem swatch="#9a7449" name="Attic earth" code="#9A7449">
          A restrained expressive color drawn from the dry, ochre ground of the
          Academy site. Use it for diagrams, circuit nodes, numeric output, and
          selected text.
        </PaletteItem>
        <PaletteItem swatch="#f0ece2" name="Pale limestone" code="#F0ECE2">
          The principal light color in dark mode. It carries the warmth of the
          stone ground rather than introducing a clinical white.
        </PaletteItem>
        <PaletteItem swatch="#c9c1b2" name="Cut stone" code="#C9C1B2">
          Rules, borders, and inactive controls. It separates information
          without competing with it.
        </PaletteItem>
      </dl>
      <p className="palette-note">
        In dark mode, olive is raised to <code>#A6A887</code>, earth to{" "}
        <code>#C09A68</code>, and cut stone deepens to <code>#49463E</code> to
        preserve contrast. Supporting surfaces and muted text are derived from
        the same stone and ink tones.
      </p>
    </section>
    <section>
      <h2>Use</h2>
      <p>
        Color should communicate state, hierarchy, or interaction. Olive
        indicates interaction; earth adds emphasis to diagrams and output.
        Neither should become decoration. Error colors may depart from the
        palette where convention requires it, but they are functional rather
        than expressive.
      </p>
    </section>
    <section>
      <h2>Typography</h2>
      <p>
        Newsreader carries propositions, titles, and moments that need
        reflection. Libre Franklin carries explanation, navigation, labels, and
        interfaces. Large type may be quiet; small type must be exact. Avoid
        unnecessary weights, ornamental italics, and artificial hierarchy.
      </p>
    </section>
    <section>
      <h2>Voice</h2>
      <p>
        Write plainly, specifically, and with intellectual confidence. Ask a
        question only when the product or the next sentence can help answer it.
        Avoid grand claims, vague philosophy, inflated metaphors, and language
        that sounds profound without saying anything.
      </p>
    </section>
    <section>
      <h2>Artwork</h2>
      <p>
        Artwork draws from the Academy as a place of inquiry, not from
        mythology. Use architecture, human scale, measured construction, worn
        fresco, vellum, stone, carbon, and evidence of revision. Figures are
        ordinary thinkers, never gods or heroes. Color remains mineral and
        sparse: stone and ink first, olive and earth second.
      </p>
    </section>
    <section>
      <h2>Interaction</h2>
      <p>
        Motion should reveal structure or state. Circuit paths expose the system
        beneath the surface; hover treatments clarify what can be opened; the
        theme switch records a considered choice. Interactions should never
        exist solely to demonstrate cleverness.
      </p>
    </section>
  </>
);

type PaletteItemProps = {
  swatch: string;
  name: string;
  code: string;
  children: ReactNode;
};

const PaletteItem = ({
  swatch,
  name,
  code,
  children,
}: PaletteItemProps): ReactNode => (
  <div>
    <dt>
      <i style={{ "--swatch": swatch } as CSSProperties} />
      <span>
        {name} <code>{code}</code>
      </span>
    </dt>
    <dd>{children}</dd>
  </div>
);

export const PrivacyContent = (): ReactNode => (
  <>
    <p>Effective date: August 26, 2026</p>
    <p>
      Gradiated Ltd (“Gradiated,” “we,” “us,” or “our”) respects your privacy.
      This policy explains what information we collect, why we use it, and when
      we share it. It applies to gradiated.com, the Gradiated console, and
      Gradiated inference services.
    </p>
    <h2>Information we collect</h2>
    <p>
      We collect information you provide, such as your name, email address,
      company, billing details, and messages to us. We also collect account,
      workspace, API key, and usage information needed to run the service.
    </p>
    <p>
      We collect limited technical information such as browser type, device
      information, IP address, and pages visited through standard web logs.
    </p>
    <h2>Inference data</h2>
    <p>
      Gradiated applies zero data retention to inference content. This policy
      also applies to requests that OpenRouter sends to Gradiated. We process
      prompts, messages, tool payloads, attachments, generated outputs, and
      request metadata to return a response. Gradiated does not persist this
      content after request processing. It may exist in volatile memory while
      the request runs.
    </p>
    <p>
      We do not use customer prompts, outputs, or other inference content to
      train, fine-tune, evaluate, rank, advertise, or improve models. We do not
      intentionally write inference content to the Gradiated product database or
      application logs.
    </p>
    <p>
      We retain limited non-content usage records, such as the model, token
      counts, timing, request status, service identifiers, and billing data. We
      use these records to provide the service, calculate charges, protect the
      system, resolve incidents, and meet legal obligations.
    </p>
    <p>
      Inference may run on contracted infrastructure providers. These providers
      may process request data temporarily to operate the runtime. If you send a
      request through another platform, that platform may process or retain data
      under its own terms.
    </p>
    <h2>How we use information</h2>
    <p>
      We use information to provide and support the service, process payments,
      respond to inquiries, communicate with you, secure our systems, prevent
      abuse, improve the service using non-content data, and comply with the
      law. We do not sell personal information.
    </p>
    <h2>Legal bases</h2>
    <p>
      We process information because it is needed to perform our contract with
      you, to meet legal obligations, or for our legitimate interests in
      operating a secure and reliable service. We use consent where the law
      requires it, such as for some marketing or non-essential cookies.
    </p>
    <h2>How we share information</h2>
    <p>
      We share information with service providers that support hosting,
      inference, payments, email, security, and analytics. We may also share
      information when required by law or in connection with a corporate
      transaction. The providers and purposes are listed on our{" "}
      <SiteLink href="/subprocessors-security/">
        Subprocessors and security
      </SiteLink>{" "}
      page. We do not sell personal information.
    </p>
    <h2>International transfers</h2>
    <p>
      We and our providers may process information in the United Kingdom, the
      United States, and other countries. Where required, we use an adequacy
      decision, the UK International Data Transfer Agreement, the UK Addendum to
      the EU Standard Contractual Clauses, or another lawful safeguard.
    </p>
    <h2>Retention</h2>
    <p>
      We keep information only for as long as it is needed for the purposes in
      this policy. We keep account, usage, security, and billing records for the
      period needed to operate the service, prevent abuse, resolve disputes,
      meet tax and accounting duties, and comply with the law. We then delete or
      anonymize it where possible.
    </p>
    <h2>Your rights</h2>
    <p>
      Depending on where you live, you may have the right to access, correct,
      delete, restrict, or transfer your personal information. You may object to
      some processing and withdraw consent where processing is based on consent.
      To make a request, email team@gradiated.com.
    </p>
    <p>
      You can complain to the UK Information Commissioner’s Office at{" "}
      <SiteLink href="https://ico.org.uk/make-a-complaint/">
        ico.org.uk
      </SiteLink>{" "}
      if you believe we have not handled your information lawfully.
    </p>
    <h2>Changes and contact</h2>
    <p>
      We may update this policy from time to time. We will post the revised
      version here. Gradiated Ltd is the controller for the personal information
      covered by this policy. Our registered office is 68 Vinery Road,
      Cambridge, CB1 3DN, England. Questions can be sent to team@gradiated.com.
    </p>
  </>
);

export const TermsContent = (): ReactNode => (
  <>
    <p>Effective date: August 26, 2026</p>
    <p>
      These Terms of Service are an agreement between you and Gradiated Ltd.
      They apply when you use the Gradiated website, console, API, inference
      services, or related documentation.
    </p>
    <h2>Using Gradiated</h2>
    <p>
      You must be old enough to enter a binding contract and have authority to
      act for your organization. You are responsible for your account, API keys,
      users, and activity. Keep API keys private and tell us at
      team@gradiated.com if you think one has been exposed.
    </p>
    <h2>Your content</h2>
    <p>
      You keep your rights in prompts, inputs, outputs, and other material you
      send to Gradiated. You give us the limited rights needed to process that
      material and provide the service. You are responsible for having the
      rights and permissions needed to send it.
    </p>
    <p>
      Model output can be wrong, incomplete, or similar to output given to other
      users. You must review output before relying on it. Do not use Gradiated
      output as the only basis for decisions about a person’s legal rights,
      health, safety, employment, housing, education, credit, or access to
      essential services.
    </p>
    <h2>Acceptable use</h2>
    <p>
      You must follow our{" "}
      <SiteLink href="/acceptable-use/">Acceptable Use Policy</SiteLink> and all
      laws that apply to your use of the service. We may limit, suspend, or end
      access if needed to protect the service, other users, or the public.
    </p>
    <h2>Third-party models and services</h2>
    <p>
      Gradiated may use open models, model runtimes, cloud infrastructure, and
      other third-party services. Their licenses and terms may apply to your use
      of a model or output. We will identify material model limits where we can.
      We do not guarantee that a model will remain available.
    </p>
    <h2>Beta service</h2>
    <p>
      Some Gradiated services are in private beta. Features, limits, pricing,
      and availability may change. The service may have errors or downtime. Do
      not use a beta service for an activity where failure could cause death,
      injury, or serious financial or legal harm.
    </p>
    <h2>Fees</h2>
    <p>
      If a service has fees, you must pay the fees shown at purchase or in your
      order. You authorize our payment provider to charge the selected payment
      method. Fees are exclusive of taxes unless stated otherwise. You are
      responsible for taxes that you must pay.
    </p>
    <h2>Our rights</h2>
    <p>
      Gradiated and its licensors own the service, software, branding, and
      documentation. These Terms give you a limited right to use them while your
      account is active. You must not copy, reverse engineer, resell, or
      interfere with the service except where the law does not allow us to
      restrict that activity.
    </p>
    <h2>Disclaimers and liability</h2>
    <p>
      To the extent allowed by law, the service is provided “as is” and “as
      available.” We exclude warranties that the law allows us to exclude. We
      are not responsible for indirect or consequential loss, loss of profits,
      or loss of data. Nothing in these Terms limits liability that cannot be
      limited by law, including liability for fraud or death or personal injury
      caused by negligence.
    </p>
    <p>
      If you use Gradiated as a business, our total liability for claims
      relating to the service will not exceed the fees you paid to Gradiated for
      the service in the 12 months before the event that caused the claim.
    </p>
    <h2>Ending the agreement</h2>
    <p>
      You may stop using the service at any time. We may suspend or end access
      for a breach, a security risk, non-payment, or where we must do so by law.
      Terms that should continue after termination will continue, such as terms
      about payment, ownership, confidentiality, liability, and disputes.
    </p>
    <h2>Law and contact</h2>
    <p>
      These Terms are governed by the laws of England and Wales. The courts of
      England and Wales will have exclusive jurisdiction, unless mandatory law
      gives you a different right. Questions about these Terms can be sent to
      team@gradiated.com.
    </p>
  </>
);

export const AcceptableUseContent = (): ReactNode => (
  <>
    <p>Effective date: August 26, 2026</p>
    <p>
      This policy explains how you may use Gradiated. It applies to all users,
      workspaces, API keys, and applications that connect to the service.
    </p>
    <h2>Do not use Gradiated to</h2>
    <ul>
      <li>Break the law or help another person break the law.</li>
      <li>
        Steal credentials, deploy malware, run scams, or gain unauthorized
        access to systems or accounts.
      </li>
      <li>
        Create or distribute content that sexually exploits or harms children.
      </li>
      <li>
        Threaten, harass, exploit, or target people based on protected
        characteristics.
      </li>
      <li>
        Evade limits, probe or disrupt the service, or interfere with another
        user’s access.
      </li>
      <li>Infringe intellectual property, privacy, or other rights.</li>
      <li>
        Make high-impact decisions about people without appropriate human
        review, notice, and safeguards.
      </li>
      <li>
        Send personal, confidential, or regulated information without the rights
        and safeguards required by law.
      </li>
    </ul>
    <h2>Responsible use</h2>
    <p>
      Check model output before you use it. Add human review for sensitive
      decisions. Use the smallest amount of personal information needed. Keep
      your keys secure and use rate limits that match your application.
    </p>
    <h2>Enforcement</h2>
    <p>
      We may investigate suspected violations. We may throttle, suspend, or
      terminate access when needed to protect users, the service, or the public.
      We may preserve and disclose information when the law requires it or when
      needed to investigate abuse.
    </p>
    <h2>Report a problem</h2>
    <p>
      Report security issues, suspected abuse, or an accidental exposure of an
      API key to team@gradiated.com. Include enough detail for us to
      investigate. Do not include secrets in the report.
    </p>
  </>
);

export const DpaContent = (): ReactNode => (
  <>
    <p>Effective date: August 26, 2026</p>
    <p>
      This Data Processing Addendum (“DPA”) applies when a customer uses
      Gradiated to process personal data and the customer is the controller or
      processor. In that case, Gradiated Ltd acts as the processor or
      subprocessor. For account, billing, and business contact information,
      Gradiated acts as a controller under our{" "}
      <SiteLink href="/privacy/">Privacy Policy</SiteLink>.
    </p>
    <h2>Instructions and scope</h2>
    <p>
      We process personal data only to provide, secure, support, and improve the
      service using non-content information. The customer’s instructions are the
      customer’s use of the service, this DPA, and any written instructions that
      we accept. The processing details are the customer’s prompts, messages,
      tool payloads, attachments, outputs, and related request metadata. The
      duration is the term of the customer’s use of the service.
    </p>
    <h2>Confidentiality and security</h2>
    <p>
      We require people who can access customer data to keep it confidential. We
      use technical and organizational measures appropriate to the risk,
      including access controls, encrypted connections, protected secrets,
      service isolation, monitoring, and incident response processes.
    </p>
    <p>
      Gradiated-controlled systems do not persist inference content after
      request processing. Gradiated does not use it to train, fine-tune,
      evaluate, rank, advertise, or improve models. Limited non-content usage
      records may remain for billing, security, reliability, and legal purposes.
    </p>
    <h2>Subprocessors</h2>
    <p>
      You give Gradiated general authorization to use the subprocessors listed
      on our
      <SiteLink href="/subprocessors-security/">
        Subprocessors and security
      </SiteLink>{" "}
      page. We will update that page when we add or replace a material
      subprocessor. We will require each subprocessor to protect personal data
      under written terms that provide protection appropriate to its role.
    </p>
    <h2>International transfers</h2>
    <p>
      We may transfer personal data outside the UK. Where required, we use an
      adequacy decision, the UK International Data Transfer Agreement, the UK
      Addendum to the EU Standard Contractual Clauses, or another lawful
      safeguard.
    </p>
    <h2>Requests and incidents</h2>
    <p>
      We will provide reasonable help with requests from data subjects, data
      protection impact assessments, regulator inquiries, and security
      obligations. If we become aware of a personal data breach affecting your
      data, we will notify you without undue delay and provide the information
      that we reasonably can.
    </p>
    <h2>Deletion and audits</h2>
    <p>
      When the service ends, we will delete or return personal data where the
      service and law allow. We may keep information that the law requires us to
      keep, subject to confidentiality and security controls. We will make
      available information reasonably needed to show compliance and will
      support reasonable audits, subject to security, confidentiality, and cost
      controls.
    </p>
    <h2>Contact</h2>
    <p>
      Contact team@gradiated.com with DPA questions or to request a signed copy
      for your organization. This DPA supplements the Terms of Service. If the
      documents conflict, this DPA controls for the processing of personal data.
    </p>
  </>
);

export const SubprocessorsContent = (): ReactNode => (
  <>
    <p>Effective date: August 26, 2026</p>
    <p>
      This page lists the main providers that support Gradiated and summarises
      the security measures used in the service. We update it when a material
      provider or processing purpose changes.
    </p>
    <h2>Inference data</h2>
    <p>
      Gradiated uses zero data retention for standard inference in its
      controlled systems. We do not persist prompts, messages, tool payloads,
      attachments, or generated outputs after request processing. This content
      can exist in memory while a request is running. We do not write it to the
      Gradiated product database or application logs.
    </p>
    <p>
      We retain limited non-content data, including model identifiers, token
      counts, timing, request status, service identifiers, and billing data. We
      use this data for billing, security, reliability, support, and legal
      obligations. We do not use customer content to train or improve models.
    </p>
    <h2>Current providers</h2>
    <ul>
      <li>
        <strong>Amazon Web Services</strong> — cloud hosting, networking,
        secrets, transactional email delivery, and supporting infrastructure.
      </li>
      <li>
        <strong>ClickHouse</strong> — storage and queries for non-content usage
        and operational metrics.
      </li>
      <li>
        <strong>Nebius and RunPod</strong> — GPU infrastructure used by selected
        inference runtimes.
      </li>
      <li>
        <strong>Stripe</strong> — payment processing and billing support.
      </li>
    </ul>
    <p>
      Provider locations can vary by service and deployment. We use the
      safeguards described in our{" "}
      <SiteLink href="/privacy/">Privacy Policy</SiteLink> and{" "}
      <SiteLink href="/dpa/">DPA</SiteLink> where required.
    </p>
    <h2>Security measures</h2>
    <ul>
      <li>Public traffic uses encrypted HTTPS connections.</li>
      <li>
        Inference services run in isolated infrastructure and are not exposed
        directly as public application endpoints.
      </li>
      <li>
        Access to secrets and operational systems is restricted through service
        credentials and access controls.
      </li>
      <li>
        We record non-content usage and operational events to support billing,
        reliability, and incident response.
      </li>
      <li>
        We review access and service behavior as part of normal operations.
      </li>
    </ul>
    <p>
      Gradiated is an early-stage service. We do not currently claim SOC 2, ISO
      27001, HIPAA, or similar certification. Contact team@gradiated.com for
      security questions or a customer security review.
    </p>
  </>
);
