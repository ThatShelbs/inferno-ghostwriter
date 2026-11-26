This Python example sits in a blog post, and the picture beside it is made by running it. It must run top to bottom as a single script (no notebook magics, no input, no files the reader does not have) and draw ONE chart.

What the chart is for: $purpose

The current code:
<code>
$code
</code>

What happened or what the author asks:
<problem>
$error
</problem>
<instruction>
$instruction
</instruction>

Rules:
- Change only what is needed. Keep the same libraries, the same chart idea, the same names and the same short, readable style; do not add features.
- Load real public data the reader can get with one import or one built-in loader (for example `vega_datasets`, or a library's own sample data). Never invent file paths or URLs.
- Keep a final line that shows the chart (`plt.show()`, `fig.show()`, `chart.show()`, `show(p)`) or saves it with the library's own call.
- Allowed imports: the standard library, pandas, numpy, matplotlib, seaborn, plotly, altair, bokeh, vega_datasets, scipy, scikit-learn, statsmodels.

Return the complete corrected script in `code` (no Markdown fences) and one plain sentence in `what_changed`.
