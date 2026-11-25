# Exporting

Open a post and click **Export**. Each platform gives you a zip bundle; Medium, Substack, LinkedIn and X also offer **Copy**, which puts the post on your clipboard as rich HTML with the images embedded, ready to paste into the platform's editor.

`thumbnail.png` is cut from the post's opening image at each platform's size: a centre crop, which every opening style is laid out to survive (everything that matters sits in the middle 5:2 band). An opening meme is padded instead of cropped, with the meme's own edge colour, so no caption is cut off. See [Opening images](images.md#opening-images).

| Platform | Bundle contents | Notes |
| --- | --- | --- |
| **Medium** | `post.html`, `post.md`, `images/`, `thumbnail.png` (1400×560, 5:2), `README.txt` | Title → title, subtitle → subtitle, sections → Medium's large heading, subsections → small heading. The opening image becomes the story preview; Medium crops it to about 2.2:1, so an opening that must stay whole (a meme) is padded to 5:2 in the pasted HTML and `images/`. |
| **Substack** | `post.html`, `post.md`, `images/`, `thumbnail.png` (1200×630), `README.txt` | The copied body excludes the title and subtitle; paste those into Substack's fields (they are listed in the README). Use the thumbnail as the social preview. |
| **LinkedIn** | `post.html`, `post.md`, `images/`, `thumbnail.png` (1920×1080 cover), `feed-post.txt`, `carousel.pdf`, `carousel.pptx`, `README.txt` | See below. |
| **X** | `post.html`, `post.md`, `images/`, `thumbnail.png` (1500×600 header), `teaser-post.txt`, `README.txt` | See below. |
| **Gumroad** | `post.pdf`, `post.html`, `post.md`, `images/`, `thumbnail.png` | Print-ready PDF for a product or post attachment. |
| **Markdown** | `post.md` with front matter (`title`, `description`, `tags`, `cover_image`, `published: false`), `post.docx`, `images/` | For dev.to, Hashnode, Ghost, static sites, or editors who prefer Word / Google Docs. |

Captions follow the "caption; credit" style under every image in all formats.

If a pasted image does not come through (editors differ in what they accept from the clipboard), drag it in from the bundle's `images/` folder.

## LinkedIn

Choose **LinkedIn** as the platform when you create the post (or make it the persona's default) and the writer follows LinkedIn's conventions: a two-line hook that survives the feed preview, one-to-three-sentence paragraphs, `##` headings only (LinkedIn articles have two heading levels and drop tables), a bolded takeaway per section, and a closing question that invites comments.

The export gives you three ways to publish:

- **Article.** *Copy article for LinkedIn* and paste into **Write article**; upload `thumbnail.png` (1920×1080) as the cover and paste the title into the title field.
- **Feed post.** The export dialog shows a feed post with a live character count (LinkedIn's limit is 3,000; only the first ~210 characters show before "…see more"). It starts as a template built from the article; **Write with Claude** replaces it with one written in the persona's voice, which is saved with the post and included as `feed-post.txt`. Markdown is stripped because LinkedIn shows it literally.
- **Document carousel.** `carousel.pdf` is a swipeable 4:5 (1080×1350) deck for a document post: a cover with the opening image, one slide per section with its key sentences, the section's diagram or chart, and a closing slide. `carousel.pptx` is the same deck, editable in PowerPoint, Keynote or Google Slides.

## X

Choose **X (Article)** as the platform and the writer follows X Article conventions: a first line that hooks (it is all the timeline shows), one-to-three-sentence paragraphs, `##` headings, bold used sparingly, lists instead of tables, short code snippets only (X Articles have no code blocks), and a close that invites replies.

- **Article.** Start an X Article, upload `thumbnail.png` (1500×600, the 5:2 header), paste the title into the title field, then *Copy for X* and paste the body. Check any code: paste long snippets as images or links.
- **Teaser post.** `teaser-post.txt` announces the article in 280 characters or fewer: the post's opening sentences that fit, then the title. Publish the article first, then share it with this text.

## Hands-on kit (GitHub)

Tutorials, how-tos, data analysis, data-viz and prompt posts are better when readers can follow along. Choose **GitHub kit** in the export dialog to turn the post into its own companion repository. The tile says *Recommended* when the post calls for one (code examples, charts, prompts, a hands-on article type, data language); it works for any post.

**Build kit** makes one Claude call (plus one retry if its code fails the checks) and lays out the files in code:

```
<post-slug>/
  notebook.ipynb              the whole article, images inline, runnable cells after the passages they serve
  article.md                  the post in Markdown, images from assets/
  data/chart_<slot>.csv       the exact numbers behind each chart in the post (from the chart's own spec)
  make_data.py                seeded synthetic data (or a library's built-in sample dataset) for everything else
  code/01_*.py                the post's main examples as standalone scripts
  prompts/starter_prompts.md  the post's prompts plus starters to adapt, with [BRACKETED] blanks
  assets/                     every image in the post, with credits.md
  requirements.txt            the packages the code imports
  README.md, LICENSE (MIT), .gitignore
```

- **Beginner code, polished charts.** Cells are short, top to bottom, with almost no functions and comments that say why. Charts have takeaway titles, labelled axes, source notes and the inferno colours (`COLORS`, defined in the setup cell). The chart library is the one the post teaches, else Altair (Vega-Lite) and Plotly Express; pick another under **Charts**.
- **The app never runs the code.** Every block is parsed, may import only the standard library and a beginner data stack, and may not shell out; a block that still fails after the retry is left out and listed. The post's own images sit next to the chart cells, so readers see the expected result.
- **Optional:** the article's live link (shown in the README and notebook) and a note for the kit ("use the public penguins dataset").
- **Download kit (.zip)** any time.

**Push to GitHub** uses your own [GitHub CLI](https://cli.github.com) sign-in; the app never sees a GitHub token. Run `gh auth login --web --git-protocol https` once in a terminal, then **Create repo & push** with a name (default: the post's slug) and **Private** (default) or **Public**. The kit's folder keeps its git history in the app's data folder, so **Push update** after a rebuild adds a commit to the same repository.

A **public** kit gets an *Open in Colab* badge: the notebook's first cell clones the repository and installs `requirements.txt` when it runs in Colab, and its images link to the repository so they show on GitHub and in Colab. Colab cannot open private repositories, so make the repository public when the post goes live (then push an update so the notebook switches to the public links).

**Add link to post** puts a short *Follow along* line with the repository (and Colab) link before the post's first section. It is a normal text revision, so *Undo* removes it.
