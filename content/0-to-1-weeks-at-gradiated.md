# 0 to 1 weeks at Gradiated

I'm new to Gradiated. I joined on Monday (three days ago). The team is small (there's 6 of us), and we're all here in Cambridge this week. It's more or less my job now to understand what the team is working on and write about it.

Write to whom?

Gradiated exists to deliver AI inference that is cheap and energy efficient. Anyone who cares how inference can get cheaper or why tokens per Joule is a useful metric should be able to follow along. The interesting developments are in the technical details, and that's hard to follow without a background in chips, inference, and models. We'd like for it not to be hard to follow. I'm not an expert in any of the above, I'm a software engineer, and whatever I need to learn to be able to follow the work, we should likely write about.


So what's going on around here?

The infrastructure to serve inference is up and running. We've rented 24 top grade GPUs (B300s) and perhaps this is obvious, but you pay per hour whether they are used or not. Our first revenue has come from offloading our unused GPU capacity to an inference marketplace such that it can be used by someone if we're not using it. If you'd like to use it, we have an API that you can use to run inference on handful of open-weight models. API keys are self-serve from a link in the docs.

This week we're speaking with our earliest customers, organizing our brand, and running internal experiments.

One such experiment is for our first post-training customer. PostHog.
It's the kind of work we'll be doing for all of our early post-training customers, and here's what I've learned about it.

### Post-training for PostHog AI

PostHog has an agent that lets you chat about the data you have in PostHog. It's a popular feature and it's $100,000/month `<is it? can we share this>` to run using a Frontier model. `<can I say which one?>`

They'd like to use an open-source model instead. To start, we sent Josh our co-founder as an FDE to investigate, benchmark and start working.

The expectation is not that open-source models out of the box are able to match the Frontier. It is more practically, how big is the difference on this specific work, and how much can we close that gap? Open-source models, by nature of being open-source, allow you to continue training the model. This is called post-training. You can teach the model how to call your specific tools, instead of having to send that information with every prompt. That alone is useful, especially for agents that call a lot of tools. But post-training can also help an open-weight model learn what good results on your work look like, and perform better.

As we have learned this week, it can also make the open-weight model perform worse.
A preliminary benchmark showed us this

`<graph where Qwen + post training is worse than base Qwen>`

Super. Surely this is unexpected I thought. But actually it was neither expected nor unexpected.
Post-training is more of a bag of tricks experimentation, rather than a deterministic pipeline of how to improve something. There are methods and techniques, but whether they will actually translate to the model learning the desired behaviour is deduced by testing it. For the PostHog, we started with a method called Supervised Fine-Tuning (SFT)

Why did we start with SFT?

> It's a standard starting place `<more on this>`, and the literature supports that a risk of using SFT in a situation like this can degrade model performance.

In a situation like what?

> The data used in post-training was pairs of what the user asked the model and what the Frontier model responded with. SFT trains the small model to answer like the Frontier model.

Ok?

> Qwen does not have the capabilities of a Frontier model. The Frontier model is confident, and it should be, it's great. But that level of confidence doesn't match Qwen's skills. Qwen may be able to solve the problem, but if it tries to solve the problem like Sonnet would it will do worse than if it just tried on its own.

That makes sense, how sure are we that this is what's happening?

> Medium confidence. It makes sense that this is what could be happening. It's a concern with "off-policy" training. Off
> because it's learning from another model and not itself. There's not a way check why the model is performing poorly, we
> just know that it is performing poorly.`<this is not totally true I think, I want to say something more specific instead>`


The above was the first experiment in a much larger plan. Josh is now working on "on-policy" post-training methods. "On" meaning Qwen can learn from it's own good and bad attempts at responding to a question. The set-up is super invovled, and requires creating a Reinforcement Learning (RL) environment. I don't know exactly what that means yet, but it's notoriously hard to do well, and the success of subsequent steps depends a lot on us being able to create a good RL environment.


---

`<unclear what to put here yet, something maybe briefly about what aidan is doing?>`


The kind of content we'll produce is still being shaped. If there's something you'd like to really understand well, email me at charley@gradiated.com
