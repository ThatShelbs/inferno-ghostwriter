Design the hands-on companion kit for this post: a small public repository with a Jupyter notebook that holds the whole article and lets readers run real code and rebuild its charts, in Google Colab or on their own machine.

Code builds the repository around your design: it copies the article into the notebook, places the post's images, writes the chart data you are given to `data/`, and adds a setup cell. You write only the code, the data recipes, short lead-ins and the starter prompts.

## Who reads the code
A beginner who just finished the article. Optimize the code for a human reading it top to bottom:
- Plain, short, intro-level Python. One idea per cell. No classes, almost no functions (one tiny helper at most when it truly saves repetition), no argument parsing, no configuration objects, no clever one-liners.
- Name things for what they are (`signups`, `monthly_revenue`), not `df2` or `tmp`.
- Comments say why, not what, and sound like the author.
- Every cell runs on its own after the cells above it. Paths are relative to the repository root (`data/...`, `assets/...`).
- Allowed imports: the standard library and $allowed. Nothing else, no shell commands, no `eval`/`exec`, no file writes outside `data/`.
- Never invent a URL, a dataset name or an API. Built-in sample datasets must be ones that library really ships. When unsure, make synthetic data.

## The charts must look professional
Readers should want to screenshot them.
- $library
- The setup cell already defines `COLORS = [$colors]` (inferno, dark to light). Use them, in order, for series; use one strong color plus gray for highlight charts.
- Every chart has a clear title that states the takeaway, a short subtitle or note with the source ("Synthetic data" when it is), labelled axes with units, readable fonts, no chart junk (no 3D, no heavy gridlines, no default legends when direct labels fit), sensible size, sorted bars.
- Recreate each of the post's charts below from its CSV so it matches the image in the post. Read the CSV with pandas; do not paste the numbers into the code.

## What to design
1. `datasets`: the data any cell needs beyond the chart CSVs below (0-3). Each recipe makes `df` from a fixed random seed (or a real built-in loader) and saves `data/<file>`; code puts every recipe in `make_data.py` and in the notebook's "Get the data" section.
2. `cells`: runnable steps that follow the article. For each Python example in the post, write a runnable version (with any data it needs) anchored on the sentence right before or after it. For data-analysis or how-to posts, add the small steps a reader needs to reproduce the results. Quote anchors exactly from the post. 3-12 cells.
3. `charts`: one per chart below (keep the slot ids), plus any plot of numbers among the other images that a reader could rebuild.
4. `scripts`: the post's main code examples as standalone scripts under `code/` (0-5), each complete and runnable from the repository root.
5. `prompts`: every prompt the post shows or describes, kept close to the post's wording, plus 2-4 starter prompts a reader could adapt to their own work on this topic. Leave [BRACKETED] blanks for the reader's details.
6. `learn`: 3-5 concrete outcomes. `description`: the repository description.

If the post has no code and no data, still make a useful kit: a small synthetic dataset that illustrates the post's main idea, a few cells that explore it, and the prompts.

Article type: $article_type

The author's note for this kit: $note

## The post's charts and other images
$charts

<article>
$markdown
</article>
