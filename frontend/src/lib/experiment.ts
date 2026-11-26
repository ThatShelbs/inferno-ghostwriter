import type { ScenarioIn } from '../api/types.gen'

/**
 * The library bake-off's starting point. Mirrors `experiments/models.py` (DEFAULT_PROMPT, default_scenarios), so change both
 * together: the author edits the prompt, and each scenario adds one line to it ("Use the Python library X").
 */
export const BAKE_OFF_PROMPT = `**Goal:** Create an exceptional, publication-quality stacked bar chart using Python.

**Context:** The visualization should reveal an interesting, thought-provoking insight while demonstrating advanced data visualization craftsmanship.

**Source:** Use a real, publicly available dataset accessible through Python, preferably involving movies, entertainment, culture, or another engaging subject. Consider the vega movie dataset. Avoid overused textbook datasets and synthetic data.

**Expectation:** Deliver 1 highly customized bar chart visualization using a discrete Viridis color palette, intentional typography, meaningful annotations, thoughtful category ordering, clear labeling, and minimal visual clutter. We are interested in advanced bar chart visualizations such as, volume stacked bar chart, percentage bar chart, diverging bar chart, radial bar chart, tornado bar chart, side-by-side bar chart, lollipop chart, waterfall bar chart, funnel bar chart. Adhere to established data visualization best practices. Provide complete, reproducible Python code that is pure minimalist for human comprehension. Also produce the resulting visualization. Please report how much code was used to generate it (line count and total character count).`

export const BAKE_OFF_SCENARIOS: ScenarioIn[] = [
  { id: 'unspecified', label: 'No library specified' },
  { id: 'matplotlib', label: 'Matplotlib', library: 'matplotlib', addendum: 'Use the Python library Matplotlib.' },
  { id: 'plotly', label: 'Plotly Express', library: 'plotly', addendum: 'Use the Python library Plotly Express.' },
  { id: 'seaborn', label: 'Seaborn', library: 'seaborn', addendum: 'Use the Python library Seaborn.' },
  { id: 'altair', label: 'Altair (Vega-Lite)', library: 'altair', addendum: 'Use the Python library Altair (Vega-Lite).' },
  { id: 'bokeh', label: 'Bokeh', library: 'bokeh', addendum: 'Use the Python library Bokeh.' },
]
