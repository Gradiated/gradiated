# Model announcements

We'd like to produce model announcement content. To decide what our target is I have 3 main questions.

1. When should we post?
2. What's our plan to stay informed?
3. What content would we like to include in our model announcement template?

## 1. When should we post?

### Thoughts

- Model announcements often happen in advance of when the weights are published. 
- Initial announcements often don't provide an expected weight drop date and say something like "within the month".
- The first announcement is usually a company blog followed by an X post. The model is then live on the provider's API immediately and on Open Router within minutes to hours.
- The model weights are usually on Hugging Face for a few minutes before the lab posts on X or publishes a blog that they're live.

Based on [The last 8 model drops](recent-model-drops.png)

TLDR: We can publish in the window between a model's public announcement and when the weights are live, but depending on what we wish to say, we can also prepare during that time and publish shortly after the model drops.

I think we should aim to publish juust after the weights go live. 
We can co-ordinate the post with the moment the model is also available on Gradiated. Often we'll get a headsup (the announcement).


## 2. What's our plan to stay informed?

- Hugging Face is the source of truth for when new model weights are live.
- OpenRouter is a good proxy for when a new model is announced/API access is available, they're almost always a day zero partner.
- Both Hugging Face and OpenRouter have free public APIs, only a few lab blogs have an RSS feed.

we could,
- Make a slack channel #model-radar
- Make a list of lab accounts we want to follow on Hugging Face, and alert when a new model is public.
- Alert when a new model is live on OpenRouter.
- Poll at some sensible rate for the data that we'll alert with.

Not looking to over-engineer this, but I do have a sense that some automated notification would be really helpful.

The lab X accounts are also useful to follow. We could go this route instead but I imagine starting with the above and following X in a non-automated way would be a good start.

## 3. What content would we like to include in our model announcement template?

I want to have a template for these announcements. 
It will help us with speed and comparing with older models and announcements.

Here are my initial thoughts:
I'd like our announcemnts to be an organized TLDR style summary that positions the model in context of the broader open-weight space. We focus on what the important and practical implications of the model release are. 

- How long since the last model relase from this lab or model family?
- What differentiates it from it's model predecessors (is it bigger, smaller, specialized)
- What kinds of work or industries might it be relevant to (who should pay attention)
- Noteworthy details, perhaps direct exerpt quotes from the lab blog announcement.

Then handy things like 
- Relevant licensing details or updates. 
    - Can you use it commericially
    - Revenue caps
    - 
- Conveninet link outs (formal model announcment blog, weights live announcement blog, hugging face, etc.)
- Relevant benchmarks?
    - I wonder if we eventually we could have some kind of Gradiated benchmark?
    - Aidan suggested this, inspired by [Fireships drawing a 3D horse metric](https://youtu.be/1FurWDiK9A4?t=150)
    - I wonder if ours could be some kind of cost or tokens per Joule metric.
