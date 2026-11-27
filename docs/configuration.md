# Configuration

Inferno Ghostwriter works with zero configuration. Most settings live in the app (**Settings**); a few can be set with environment variables or a `.env` file at the repository root (copy `.env.example`).

## In the app

| Setting | Where | Default |
| --- | --- | --- |
| Claude connection: Anthropic API or your Claude subscription | Settings → Claude | Anthropic API |
| Claude sign-in or API key | Settings → Claude | none |
| Optional subscription connections and routing | Settings → Optional models | Claude for every stage, additional uses off |
| Model | Settings → Advanced | `claude-opus-5-5` |
| Voice editing passes | Settings → Advanced | 1 |
| Refusal fallback | Settings → Advanced | on |
| Run example code (draw hands-on data viz images by running the Python example above them) | Settings → Advanced | off |
| AI-detection judge (twin test) | Settings → Advanced | on (the free scan always runs) |
| Humanize rounds | Settings → Humanizing | 1 |
| AI detectors | Settings → Humanizing | the built-in light check; trained models are optional (one-time ~1.3 GB download) |
| Theme | Settings → Appearance, or the sidebar toggle | match system |
| Persona name, byline, credit format, visual style, web research | Personas → (persona) → Settings & defaults | from the voice profile |
| Voice profile settings: profile length, words read per sample, minimum sample length, influence weight | Personas → (persona) → Settings & defaults | about 2,000 words, whole samples, every sample, influence 5/10 |
| Edits learned from your changes and feedback (review or forget) | Personas → (persona) → Settings & defaults | learned automatically |
| Image brand kit for one post: style, palette, font, motif | New post → Customize, or the post's **Image brand kit** card | the persona's visual style |
| Default dials for new posts: length, images, references, humor, storytelling, opinion strength, formality, technical depth, skimmability, education level, code, platform | Personas → (persona) → Settings & defaults | 1,500 words, automatic images, humor 5, style dials 5 ("as I write"), intermediate, code where it helps, Medium |
| Formula: article type, opener, body, closer, your own instructions for each, saved formulas ([formulas.md](formulas.md)) | New post → Formula; **Edit brief & settings**; Personas → (persona) → Settings & defaults → Default formula | automatic: the shape your voice profile describes |
| Per-post brief, persona, platform, audience and every dial | New post → Customize; on a written post, **Edit brief & settings** (regenerates the post) | the persona's defaults; audience = your usual readers |
| Voice profile version in use | Sidebar persona switcher, or the Voice profile tab | always the latest |

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `INFERNO_GHOSTWRITER_DATA_DIR` | Where the database, samples, voice profiles, images and exports live | `./data` |
| `INFERNO_GHOSTWRITER_PORT` | Port for the local app | `8732` |
| `INFERNO_GHOSTWRITER_SEED_SAMPLES_DIR` | Folder offered for one-click import of your writing | `./my_writing_examples` |
| `INFERNO_GHOSTWRITER_CLAUDE_CONNECTION` | `api` (Console credits) or `subscription` (your Pro/Max plan through Claude Code) | `api` |
| `INFERNO_GHOSTWRITER_MODEL` | Claude model | `claude-opus-5-5` |
| `INFERNO_GHOSTWRITER_USE_FALLBACKS` | Server-side refusal fallback | `true` |
| `INFERNO_GHOSTWRITER_REVISION_PASSES` | Editing passes per post | `1` |
| `INFERNO_GHOSTWRITER_EFFORT_*` | Effort per task: `ANALYZE`, `RESEARCH`, `SYNTHESIZE`, `PLAN`, `DRAFT`, `CRITIQUE`, `IMAGES`, `MEME_IDEAS`, `OPENING_IDEAS`, `IMAGE_IMPROVE`, `DETECT`, `INSIGHTS`, `REFERENCES`, `EVOLVE`, `IDEA_RESEARCH`, `IDEA_IDEAS`, `IDEA_RANK` | see `config.py` |
| `INFERNO_GHOSTWRITER_IMAGE_JUDGE` | The image judge that ranks pitches and looks at the drawn candidates, `model:effort` (model `opus`, `sonnet`, `haiku` or an id); see [images.md](images.md#one-room-for-every-image) | `opus:medium` |
| `INFERNO_GHOSTWRITER_IMAGE_CANDIDATES` | How many pitches a fresh opening image or meme gets (a meme draws all of them by code) | `6` |
| `INFERNO_GHOSTWRITER_IMAGE_BUILDS` | How many of the opening pitches are built for the judge (the best of different styles) | `3` |
| `INFERNO_GHOSTWRITER_IMAGE_REFINE` / `_IMAGE_REFINE_BELOW` | How many of the judge's best are rebuilt with its fix, and only when they score below this (1-10) | `1` / `8` |
| `INFERNO_GHOSTWRITER_IMAGE_BODY_CANDIDATES` | The same for an in-body image (diagram, chart, illustration, screenshot, icon); `1` draws straight from the brief | `3` |
| `INFERNO_GHOSTWRITER_IMAGE_FINALISTS` | How many judged candidates are kept for you to swap between | `3` |
| `INFERNO_GHOSTWRITER_IMAGE_REFERENCE_DIR` | Your local reference library of example images the judge compares against (git-ignored; optional); see [images.md](images.md#the-reference-library) | `examples/` at the repository root (`references` in the app folder for the installed app) |
| `INFERNO_GHOSTWRITER_REFERENCE_MAX_SEARCHES` | Web searches per reference | `3` |
| `INFERNO_GHOSTWRITER_OPENING_MAX_SEARCHES` | Web searches for the numbers behind a data opener (chart or big number) | `4` |
| `INFERNO_GHOSTWRITER_IDEA_MAX_SEARCHES` | Idea Lab: web searches per research scout at standard depth | `8` |
| `INFERNO_GHOSTWRITER_IDEA_WINDOW_DAYS` | Idea Lab: how many days back the feeds and scouts look | `14` |
| `INFERNO_GHOSTWRITER_CHECK_REFERENCE_LINKS` | Fetch each reference URL once and drop the ones that are gone | `true` |
| `INFERNO_GHOSTWRITER_DEMO` | Demo mode (canned responses) | `false` |
| `INFERNO_GHOSTWRITER_DEMO_SEED` | In demo mode, start an empty database with the example persona and post | `true` |
| `INFERNO_GHOSTWRITER_NO_BROWSER` | Do not open a browser on start | unset |
| `ANTHROPIC_API_KEY` | Claude API key (overrides *Sign in with Claude*) | unset |
| `INFERNO_GHOSTWRITER_AI_DETECTION` | Twin test (or Claude judge) in the AI-detection report | `true` |
| `INFERNO_GHOSTWRITER_HUMANIZE_ROUNDS` | Humanize rounds after the editor's pass (0-2) | `1` |
| `INFERNO_GHOSTWRITER_DETECTOR_MODELS` | Detectors to use, any mix of `light`, `curvature`, `classifier` (JSON list; `[]` turns them off) | `["light"]` |
| `INFERNO_GHOSTWRITER_DETECTOR_ZERO_SHOT_MODEL` | Fast-DetectGPT language model (Hugging Face id) | `openai-community/gpt2` |
| `INFERNO_GHOSTWRITER_DETECTOR_CLASSIFIER_MODEL` | AI-text classifier (Hugging Face id) | `fakespot-ai/roberta-base-ai-text-detection-v1` |
| `INFERNO_GHOSTWRITER_TWIN_PAIRS` | Passages in the twin test | `4` |

Values saved in the app (connection, model, passes, fallback, AI-detection judge, humanize rounds, detector models, image candidates) take precedence over environment defaults. **Settings → Image candidates** sets the four room numbers above at once: *Lean* (default, the values shown) or *Max quality* (every opening pitch built, three in-body candidates, every finalist refined; several times the model calls).

Every job records who did the work in its `usage.by_model` (calls and tokens per provider and task). `backend/scripts/usage_report.py` prints the same per-task breakdown for the demo post for free, so a prompt or room change can be measured before a real run.

## Claude credentials, in order

1. An API key saved in Inferno Ghostwriter (OS keychain).
2. `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` in the environment.
3. The active Anthropic CLI profile from *Sign in with Claude* (`ant auth login`).

An environment API key silently overrides a signed-in profile; the Settings page warns you when that happens.

These apply to the **Anthropic API** connection only.

## Using your Claude subscription (Pro or Max)

Choose **Settings → Claude → Claude subscription** to have Inferno Ghostwriter use your Claude plan instead of API credits.

How it works: Anthropic does not let third-party apps sign in with a Claude.ai account or use subscription credentials themselves ([Anthropic's policy](https://code.claude.com/docs/en/legal-and-compliance)). It does allow you to use your own subscription in the unmodified Claude Code CLI. So Inferno Ghostwriter runs *your* Claude Code in headless mode (`claude -p`) for every model call. Inferno Ghostwriter never sees your Claude credentials.

Setup:

1. [Install Claude Code](https://code.claude.com/docs/en/setup) and keep it current (`claude update`). New models need recent versions; for example, Claude Opus 5.5 needs Claude Code 2.1.280 or newer.
2. In Settings, choose **Claude subscription**, then **Sign in with Claude** if you are not signed in. This runs Claude Code's own `claude auth login` in your browser. Pick your Claude account, not Console.
3. Click **Test connection**. It shows your plan (for example "Claude Pro plan") without using any of your limits.

What to expect:

- Usage counts toward your plan's 5-hour and weekly limits. A full post with images is many calls. When you hit a limit, the error says when it resets, and you can switch to the API meanwhile.
- Each call is isolated. Inferno Ghostwriter's prompt replaces Claude Code's own system prompt, and the call runs with no tools (web search only for research), no MCP servers, no settings, hooks or CLAUDE.md, no saved session, and an empty working folder. Claude Code still adds a little context of its own, such as today's date.
- `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are removed from Claude Code's environment, because Claude Code would otherwise bill the API instead of your plan.
- The refusal fallback and Inferno Ghostwriter's prompt-cache hints do not apply. Claude Code handles caching, retries and thinking itself.
- Inferno Ghostwriter runs at most three Claude Code processes at once.

## Optional subscription models

Open **Settings → Optional models** after connecting Claude. The app offers two optional connections.

| Connection | Model | Sign-in |
| --- | --- | --- |
| ChatGPT via Codex | GPT-6.2 Sol (Medium) | Install the [Codex CLI](https://developers.openai.com/codex/cli) and choose **Sign in with ChatGPT**. The app can reuse your existing Codex ChatGPT session. |
| Google Gemini via Antigravity | Gemini 4 Argon (Medium) | Install the [Antigravity CLI](https://antigravity.google/docs/cli-getting-started) and choose **Sign in with Google**. In the terminal, complete Google's authorization flow. On macOS and Linux, run `agy acp --login` in your terminal. |

Choose **Test connection** to run a small structured request. This uses a little of the connected account's model quota. Model access and limits depend on the account and plan. Google moved consumer subscription access from Gemini CLI to Antigravity. [Google's migration announcement](https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/)

Writing stages start on Claude and the additional uses below are off. **Image work** is different: it is on **Auto** by default, so once a model is signed in it takes the image work that suits it and Claude is the fallback (see below). Ways to use the controls:

- **Keep writing at the Claude limit.** Enable one or both quota fallbacks. The order you enable them is the order the app tries them. The fallback covers eligible text stages such as planning, drafting, revising and tweaking. A successful handoff replaces any partial text in the live preview.
- **Split the editing work.** Keep Claude on the first draft, use Gemini for editorial critique, and use GPT-6.2 Sol for voice revision or a later tweak. The pipeline still uses your selected persona, voice material and the existing article checks.
- **Get more perspectives before committing.** Add guest pitches to Idea Lab, opening images, memes and in-body images. The app checks for duplicates and runs the existing ranking or panel. Optional judges add a text vote on pitches, and Codex can also review the rendered candidates. Claude designs the artwork and leads judging when it can review the candidates.

**Image work (Auto).** Each kind of image work goes to the signed-in model that fits it, and to Claude when none is signed in or a call fails:

| Image work | Auto sends it to | Why |
| --- | --- | --- |
| Ideas (opening, meme and in-body pitches; a redraw's critique) | ChatGPT, else Gemini | Text-only creative work |
| Charts, diagram and template fills, data-art settings, meme restages | ChatGPT, else Gemini | Small structured specs that code draws |
| Hand-drawn SVG (visual metaphors, illustrations, icons, screenshots) | Claude | Claude's SVG and the figure library are the reference for vector quality |
| Picture judge | ChatGPT | It can see the candidates; Claude Code cannot |

Each choice can be pinned to Claude or one model. With **ChatGPT's own image generation** on (the default, `images.raster`, set in the same card), ChatGPT generates a share of each kind of image instead of code drawing it: `images.native_share` (default 0.6) of illustrations, icons and visual-metaphor openers, `images.meme_share` (0.8) of memes in famous, comic and caption formats, and `images.art_share` (0.8) of data art openers. Each redraw rolls again. It is one or the other per image, never an extra rival, and code draws the image if generation fails. A generated meme is painted whole with its words (the judge checks the spelling, and *Words* paints it again); any other generated image has no words in it (captions and credits stay on the page). A generated image is credited to *GPT image generation (ChatGPT)*, and can be redrawn, remixed, edited by instruction (GPT is shown the current picture) or replaced like any other image. Credits name the model that designed each image. For one image, *Ideas*, *Remix* and *Edit* also offer a **Model** choice while an optional model is signed in (`RedrawIn.model` / `ImageEditIn.model`, `llm/router.image_model`): the chosen model does that job's pitches, designs and drawings, the judge keeps its seat, and Claude or Gemini turn GPT generation off for that job and ChatGPT forces it (the edit of a generated image always goes to GPT). A typical post with ChatGPT signed in uses a handful of Claude calls for images instead of several dozen.

Claude handles web research. When Claude's quota is exhausted, eligible text can finish while images that need a new Claude call may fail separately. Optional providers receive the context needed for their selected tasks, which can include the private brief, voice excerpts, article text, image references or candidate thumbnails. The app keeps routing preferences locally and leaves credentials with the CLI that owns the session. Disable all uses of a provider in Settings whenever you want to stop sending it work.

## Run example code

Hands-on data viz images ([images.md](images.md#hands-on-data-viz)) are made by running the Python example above them. This is off by default: turn on **Settings → Run example code** (`allow_code_execution`) to allow it. Each block is checked first (allowed libraries only, no shelling out, no `eval`) and then runs on this computer in an empty scratch folder through `uv run --no-project --with <libraries>`, with an environment that has none of your keys, tokens or the app's secrets, a time limit, and its process tree stopped on timeout. It is a guarded local process, not a hard sandbox, so leave it off if you do not want the app to run code on your computer. It needs uv, and Bokeh or Plotly charts also need Edge or Chrome to be saved as pictures. While it is off, the **Hands-on charts** dial resolves to *none*. The kit never runs code.

## GitHub (hands-on kits)

Pushing a [hands-on kit](exporting.md#hands-on-kit-github) uses the GitHub CLI and git already on your machine. Install the CLI from [cli.github.com](https://cli.github.com) (Windows: `winget install GitHub.cli`), then sign in once:

```bash
gh auth login --web --git-protocol https
```

The app runs `gh` and `git` as separate programs with prompts turned off and without its own API keys in their environment; it never reads or stores a GitHub token. The export dialog shows who is signed in. Without the CLI you can still build and download kits.

## Command line

```bash
uv run --project backend inferno-ghostwriter --help
```

```text
--host HOST   --port PORT   --open (browser)   --reload (development)   --demo
```
