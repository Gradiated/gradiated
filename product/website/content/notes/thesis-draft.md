# Thesis

Intelligence is still extraordinarily early. Frontier labs claim AGI, yet economic growth remains ordinary. The models exist; the products and infrastructure that turn them into useful work mostly do not. The engine may be running, but the car is not built.

Most AI software still waits for a person to ask a question. That will change. Software is becoming increasingly proactive: it can research, plan, use tools, and keep working in the cloud for hours. We think this will create enormous demand for inference over time. But that does not mean there is enormous demand for another provider of open-weight models today. Having GPUs and serving a model well gives nobody a reason to choose us on its own.

Electricity followed a similar path. Factories first replaced steam engines with electric motors to do the same work more cheaply. Once power became cheap and widely available, it reorganized industry and made entirely new products possible. Intelligence will do the same, but only when it becomes practical to use far more of it.

If intelligence becomes as important as electricity, who controls it matters enormously. We don't want a world where a handful of companies get to decide what everyone else can build, on what terms, and at what price. The more work we entrust to models, the more power we hand to whoever controls them.

We think people should be able to run, adapt, and build businesses around models they can keep using independently of the company that created them. Intelligence should be something people can build on everywhere. That is the future we want Gradiated to help create.

## The Quality:Cost ratio is the bottleneck

We initially expected customers to be very sensitive to inference prices. In practice, it turned out that the harder question is whether they can use an open-weight model at all. If it already costs a tenth of the frontier model they use, making it another 20% cheaper matters little if their agent stops working.

As models become more capable, people give them more complex jobs. The quality bar keeps moving. Growth in open-model token volume on a marketplace does not tell us whether those models can do a particular customer's work, and a good benchmark score does not settle that either. Intelligence is multidimensional. We need to measure the things that matter for the job.

But believing in open models doesn't make them good enough. Customers shouldn't have to accept a worse agent to support a more open future. Our job is to make open models a practical choice: get them to do useful work reliably, at a cost that makes switching worthwhile.

## Inference should fit the work

Working with customers has shown us that many teams do not have good evals for their agents. Even sophisticated teams often ship changes because they seem better. Before we can tell whether a cheaper model is good enough, we need a useful way to tell whether we have made the agent worse.

Production traces and the customer's codebase are a useful starting point. They contain the inputs, situations, and failures that actually occur, which are hard to invent from scratch. With multiple customers, we have used them to build evals and reinforcement learning environments around the work their agents do.

Gradiated is building tools to turn that understanding into models shaped around particular workloads. We start with custom trained decision models - these can understand based on production workloads if a given prompt is simple or hard, and thus where to send it, and can route and learn dynamically.

The second step is developing post trained models for people cost-effectively. We do this by optimizing prompts against the environment first, then fine-tuning a model using the results. Here it's early, but the initial results are promising. Making this reliable and economical across customer workloads is the work ahead.

## Training has to pay for itself

A technically successful experiment can still be a bad deal. If a company spends $1K a month on inference, spending $30K on training is difficult to justify even if its inference bill falls close to zero. The quality gain, training cost, serving cost, and time to benefit all matter.

We want the quickest economical route to a model that does the job. Sometimes prompt optimization may be enough. Sometimes fine-tuning may make sense. The customer needs a working agent on secure, reliable infrastructure, with economics that justify changing what they already use.

All of this we gradually want to evolve into an SDK rather than us doing this work manually.

## Start with a specific job

Our early inference traction has come from specific use cases. We think there is a better business in getting a model to do one particular job well than in offering the same general-purpose model as a dozen other providers.

Nor does an open model need to replace a frontier model across an entire workload. A router trained around a customer's work could send simpler tasks to an open model and leave harder tasks with the frontier model. We are exploring whether this is a more practical starting point than trying to close the whole quality gap through training.

We plan to release specialized models for problems we have experienced ourselves through the software development lifecycle - for things such as merging diffs, CI, cybersecurity or routing. We think useful models can earn distribution and bring customers to our tools for training bespoke models, and we can start with the smaller, simpler models. Later, we will make money by running inference on those models.

## Make the economics work

Optimization remains important. Better runtimes, kernels, scheduling, and infrastructure improve our margins and can improve reliability. Those improvements become much more valuable once we have customers with useful work for the models to do.

We will avoid large compute commitments ahead of demonstrated demand. Buying or leasing GPUs does not solve the problem of finding something valuable to do with them. Over time, sufficiently large and stable workloads may justify specialist hardware or our own silicon. That decision should follow the workload and the economics.

The sequence is:

1. Find a specific job that matters to a customer.

1. Build evals that tell us whether we are doing it well.

1. Improve prompts, models, or routing until the quality and economics make sense.

1. Serve the workload reliably and earn more demand.

1. Optimize the underlying systems as that demand grows.

## Why now

Teams are giving agents increasingly complex work, but many still lack a reliable way to evaluate them or adapt models to their own tasks. This means they spend more and more on frontier models, with large chunks of this spend being totally needless. We think helping customers cross that gap is a useful business to build now.

If Gradiated succeeds, every workload gets the intelligence it actually needs: accurate, fast, and cheap, in the combination that matters for that work. As we do this, we'll ship many useful open source models and make it economical for companies to develop models around their own work. More people will be able to build with intelligence they can run, change, and control.

We believe in an open source, distributed model future, with millions of companies making intelligence useful in different ways. Getting more useful work from each unit of compute, and giving much freer access to as many models as possible will let more people and systems research, build, understand, and do more. We don't want the world's capacity to do those things to depend on the permission of a few frontier labs.
