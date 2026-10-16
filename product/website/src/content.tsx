import type { ReactNode } from "react";
import { SiteLink } from "./components/SiteLink";
import { articles } from "./articles";

export type Note = {
  slug: string;
  date: string;
  title: string;
  description: string;
};

export const notes: Note[] = articles
  .filter((article) => article.path.startsWith("/notes/"))
  .map((article) => ({
    slug: article.path.split("/")[2],
    date: article.status === "draft" ? "Draft" : article.publishedAt,
    title: article.title,
    description: article.description,
  }));

export const ThesisContent = (): ReactNode => (
  <>
    <p>
      Intelligence is still extraordinarily early. Frontier labs claim AGI, yet
      economic growth remains ordinary. The models exist; the products and
      infrastructure that turn them into useful work mostly do not. The engine
      may be running, but the car is not built.
    </p>
    <p>
      Most AI software still waits for a person to ask a question. That will
      change. Software is becoming increasingly proactive: it can research,
      plan, use tools, and keep working in the cloud for hours. This is logical
      because proactive software is objectively better than reactive, once users
      can trust it. As more real work moves into these systems, demand for
      inference will be close to insatiable.
    </p>
    <p>
      Electricity followed a similar path. Factories first replaced steam
      engines with electric motors to do the same work more cheaply. Once power
      became cheap and widely available, it reorganized industry and made
      entirely new products possible. Intelligence will do the same, but only
      when it becomes practical to use far more of it.
    </p>
    <h2>Inference should fit the work</h2>
    <p>
      Inference is usually sold as if every request has the same requirements.
      It does not. A person waiting for an answer cares about latency. A cloud
      task running for hours may care much more about accuracy, reliability, and
      cost. Today developers compare providers, benchmarks, prices, and latency,
      then commit to a compromise they cannot properly control.
    </p>
    <p>
      Gradiated provides inference designed for the workload. We turn its traces
      into an RL environment, build the evals, and post-train an open model
      automatically. The developer just changes the base URL. The result is a
      model shaped around the work it actually performs, with direct control
      over the tradeoff between latency and cost.
    </p>
    <h2>Open models are taking the market</h2>
    <p>
      Open-weight models are not merely growing with inference. They are taking
      share from closed models. Between September 2025 and August 2026, their
      share of OpenRouter tokens rose from 26% to 60% for requests originating
      in the US and from 16% to 65% in the EU. Open models overtook closed
      models in both regions in early 2026, according to OpenRouter&apos;s{" "}
      <SiteLink href="https://openrouter.ai/blog/announcements/us-in-region-routing/">
        regional usage data
      </SiteLink>
      .
    </p>
    <p>
      That change is happening inside a market that is itself compounding.
      <SiteLink href="https://openrouter.ai/blog/announcements/series-b/">
        OpenRouter&apos;s weekly volume grew fivefold in six months
      </SiteLink>
      , from 5 trillion to 25 trillion tokens. By September 2026, nine of its
      ten most used models by 30-day token volume were open-weight, according to
      its <SiteLink href="https://openrouter.ai/data/">usage data</SiteLink>.
    </p>
    <p>
      OpenRouter is one marketplace, not the whole market. But its direction is
      hard to ignore. Open weights can be post-trained, measured, and served in
      different ways. No single model will be best for every task simply because
      using a general purpose, many parameter model is less efficient to serve,
      and post-trained models frequently have better task-specific performance.
    </p>
    <h2>Go all the way down</h2>
    <p>
      Assume inference becomes a commodity. Reliability and trust are table
      stakes, in the same way a gas station would go out of business near
      instantly if its fuel wasn't good enough for cars to use. Beyond that, the
      provider that can deliver the most useful intelligence with the least
      wasted computation wins.
    </p>
    <p>
      At the extreme, that requires control of the whole stack. A model&apos;s
      architecture determines its memory access. The runtime and kernels
      determine how much of the hardware is used. Scheduling and infrastructure
      determine whether expensive capacity sits idle. Eventually, the workload
      should determine the silicon itself where possible.
    </p>
    <p>
      General-purpose accelerators must support almost anything. We do not need
      to. Sparse mixture-of-experts models such as Kimi K3 activate only part of
      the model for each forward pass. Their ideal memory layout, interconnect,
      and scheduling are different from those of a dense model. A chip designed
      around a small number of known model families can be simpler and much more
      efficient than one designed around every possible model.
    </p>
    <p>
      We are building an end-to-end simulation environment so that software and
      hardware can be designed together. It lets us test compilers, runtimes,
      memory hierarchies, and silicon before tape-out, then change the design as
      models and workloads change.
    </p>
    <h2>There is a boring way to do this</h2>
    <p>
      We start with a reliable inference service on existing GPUs. Real usage
      tells us which models matter, how long requests run, what latency they
      need, and where computation is wasted. We optimize those model families,
      post-train them for customer workloads, and sell unused capacity through
      marketplaces.
    </p>
    <p>
      We do not need to guess at a chip on day one. The API collects its
      requirements first. Once the workload is clear and the volume is there, we
      can build a straightforward chip around the parts that matter. Then we
      repeat the same process at the data-centre level.
    </p>
    <p>The sequence is:</p>
    <ul>
      <li>
        Use traces to build evals and RL environments, then post-train models
        for the workload automatically. Provide trusted open-model inference
        with latency configurability as a by-product.
      </li>
      <li>
        Optimize the model, runtime, kernels, scheduling, and infrastructure as
        one system.
      </li>
      <li>
        Turn the requirements learned from real demand into silicon and get to
        the scale where we can buy specialist chips if needed for workloads our
        own silicon cannot service.
      </li>
      <li>
        Repeat, using the efficiency to drive more scale, to the point where we
        can get to data center scale and beyond. We will lose eventually if we
        do not go this deep.
      </li>
    </ul>
    <h2>Why now</h2>
    <p>
      The model landscape is still moving, open weights have crossed from the
      minority to the majority on a major marketplace, and no inference provider
      has won the market. Distribution matters because scale lowers purchasing
      costs, makes specialization worthwhile, and funds the next layer of the
      stack. The market is open now. It will not remain open forever.
    </p>
    <p>
      If Gradiated succeeds, every workload gets the intelligence it actually
      needs: accurate, fast, and cheap, in the combination that matters for that
      work. Ultimately, driving down tokens per joule we believe is the greatest
      impact we can have on mankind as it is the best way to empower every
      person and every system to research, build, understand and do more.
    </p>
  </>
);

export const PrivacyContent = (): ReactNode => (
  <>
    <p>Effective date: August 26, 2026</p>
    <p>
      Gradiated, a division of PostHog Inc. (“Gradiated,” “we,” “us,” or “our”),
      respects your privacy. This policy explains what information we collect,
      why we use it, and when we share it. It applies to gradiated.com, the
      Gradiated console, and Gradiated inference services.
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
      version here. Gradiated is the controller for the personal information
      covered by this policy. Our address is PostHog Inc., 2261 Market Street,
      Suite 4008, San Francisco, CA 94114, United States. Questions can be sent
      to team@gradiated.com.
    </p>
  </>
);

export const TermsContent = (): ReactNode => (
  <>
    <p>Effective date: October 4, 2026</p>
    <p>
      These Terms of Service are an agreement between you and Gradiated, a
      division of PostHog Inc. They apply when you use the Gradiated website,
      console, API, inference services, or related documentation.
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
    <h2>Inference availability</h2>
    <p>
      Paid production inference is covered by our{" "}
      <SiteLink href="/sla/">Service Level Agreement</SiteLink>, which forms
      part of these Terms. It sets out our uptime commitment, eligible service
      credits and how to claim them. Its express commitments apply despite the
      general disclaimers below.
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
      These Terms are governed by the laws of the State of Delaware, United
      States. The state and federal courts located in Delaware will have
      exclusive jurisdiction, unless mandatory law gives you a different right.
      Questions about these Terms can be sent to team@gradiated.com.
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
      processor. In that case, Gradiated, a division of PostHog Inc., acts as
      the processor or subprocessor. For account, billing, and business contact
      information, Gradiated acts as a controller under our{" "}
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
        <strong>RunPod</strong> — GPU infrastructure used by selected inference
        runtimes.
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
