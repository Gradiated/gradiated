# Kimi K3.1 Pro vs Opus 5.5 inside Saltfish Studio's Max pipeline

- **Question:** can Kimi K3.1 Pro (our `api.gradiated.com` deployment) replace Opus 5.5 as the agent in Saltfish's Max pipeline, the tier where one agent writes the ideas and the script and builds every scene?
- **Setup (2026-11-10):**
  - Saltfish's `Saltfish-AB/editor-lek` at `main` `f7a6ef7` (private repo, cloned outside this repo), run locally with its Postgres and two dev servers on one database.
  - **Opus arm:** production seats; `director`, `build` and `critic` all `claude-opus-5-5` at effort high.
  - **Kimi arm:** `director` and `build` switched to Kimi through `V2_MODEL_DIRECTOR` / `V2_MODEL_BUILD`.
  - **Critic:** Opus 5.5 in both arms.
  - **Routing:** `router.py` serves Saltfish's Anthropic SDK calls. The alias `claude-kimi-k3-1-pro` goes to our gateway's `/v1/messages`; everything else goes to the CLIProxyAPI subscription proxy.
  - **Local-only change to Saltfish:** a `lib/meter.ts` price row for the alias ($1/$9/$0.10 per M); nothing committed or pushed to Saltfish.
- **Held the same in both arms:**
  - **Brand:** the fictional `acme` test kit from their repo.
  - **Sources:** the same source text ([sources/](sources/)) and the same brief: 45 s, 16:9, music-only.
  - **Customer policy (`drive.py`):** pick the first idea, approve the script as written.
  - **Render:** Saltfish's own renderer (`lib/render.ts`).
- **Deviations from Saltfish production:**
  - There is no Gemini key, so the Gemini seats (summary, scenes, ask, locate, describe) ran on `claude-sonnet-5` in both arms.
  - There is no ElevenLabs key, so the videos are music-only.
- **Evidence labels:**
  - **Measured:** cost, turns, time.
  - **Judge-derived:** blind pairwise verdicts (`judge.py`). Opus 5.5 and GPT-6.1 Sol, both orders, contact sheets at 1 fps plus the opening at 4 fps.
  - **Human (agent) review:** contact sheets in [figures/](figures/).

## Results (n = 2 briefs × 1 run per arm)

| video | arm | turns | cost (Saltfish meter, list price, incl. Opus critic) | Make → done | judge wins | mean overall /10 |
|---|---|---|---|---|---|---|
| Auto-file launch | Opus 5.5 | 66 | $6.92 | ~29 min | 4/4 | 7.0 |
| Auto-file launch | Kimi K3.1 | 56 | $1.82 | ~11 min | 0/4 | 5.0 |
| Reminders how-to | Opus 5.5 | 44 | $5.70 | ~23 min | 4/4 | 7.0 |
| Reminders how-to | Kimi K3.1 | 105 | $2.47 | ~16 min | 0/4 | 5.25 |

- **Quality:**
  - Opus won 8/8 blind verdicts. Both judges agree, and the order flip does not change any verdict.
  - The judges' "off-palette" notes against Kimi are wrong: the rubric listed only chalk, ink and grape, but the Acme kit also defines moss and sun. Their other defects are real and match the human review:
    - guide lines striking through text (Auto-file 0:05–0:08);
    - cards clipped or overlapping at transitions (0:33–0:39);
    - grey skeleton rows where content should be, and near-empty frames (how-to 0:05, 0:09, 0:30);
    - tiny secondary text.
  - Opus films have defects too: folders clipped mid-transition at Auto-file 0:20, and a few sparse frames.
  - Opus's main advantages:
    - a problem-to-solution hook ("Saved somewhere?" → 3 hours lost → Introducing Auto-file);
    - concrete, readable UI with real data and a timeline that reacts to each step.
- **Reliability:**
  - No provider errors in either arm. Saltfish's tools, adaptive thinking, the 1-hour cache and strict tool schemas all worked on Kimi through the gateway.
  - The Kimi how-to run hit Max's 90-step build cap while revising, so it shipped its first cut (Saltfish's designed fallback). Kimi takes many short turns; Opus takes fewer, longer ones.
- **Cost and speed:**
  - Kimi is about 3× cheaper and about 2× faster per video.
  - Saltfish's production Max average on Opus 5.5 is $7.36 (from their HANDOFF).
- **Read:**
  - Kimi K3.1 Pro is a working drop-in for the Max agent: it completes videos end to end at about a third of the cost.
  - It is not yet at Opus's quality on Saltfish's product. Judges put it about 2 points lower on a 10-point scale, and the gap is mostly craft (layout, clipping, placeholder content) and story framing.
  - n = 2 per arm, one judge family per vendor; treat this as directional.

## Re-running

1. Clone `Saltfish-AB/editor-lek`. In `studio/`: `npm ci`, `./setup-local.sh`, `npm run db:migrate`, then copy `test-support/kits/acme` to `brands/acme` and run `node db/kit-docs-sync.ts import acme` (Node 24 via mise).
2. `python3 router.py`. Start the two servers with the env in [serve.sh](serve.sh): `ANTHROPIC_BASE_URL` set to the router, plus the `V2_MODEL_*` overrides for the Kimi arm.
3. Per arm, through the API: create the video, add the source, propose the brief on one arm, then PUT the same brief to both arms and POST `/director {effort:"max"}`. Then run `python3 drive.py <port> <video_id>`.
4. `python3 judge.py <pair> <opus.mp4> <kimi.mp4>`.

Films, transcripts and logs stay untracked under `.agents/runtime/saltfish_compare/`.
