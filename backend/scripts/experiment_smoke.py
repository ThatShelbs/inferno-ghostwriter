"""Check, for free, that the experiment sandbox can really draw a chart with each of the six libraries on this machine.

Runs a small canned stacked bar chart (Vega movies: films per genre, stacked by MPAA rating) per library through the real
``LocalSandbox`` (uv, a throwaway environment, Edge or Chrome for Bokeh and Plotly pages) and writes the PNGs.

    uv run python scripts/experiment_smoke.py [output_folder] [library ...]

No model is called, so it costs nothing. Needs uv and network access the first time (to fetch the libraries).
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from inferno_ghostwriter.authenticity.local_detector import find_uv
from inferno_ghostwriter.sandbox import LocalSandbox, find_browser

PREP = """from vega_datasets import data

df = data.movies().dropna(subset=["Major_Genre", "MPAA_Rating"])
table = df.groupby(["Major_Genre", "MPAA_Rating"]).size().unstack(fill_value=0)
table = table.loc[table.sum(axis=1).sort_values().index]
"""

CODE = {
    "matplotlib": PREP
    + """import matplotlib.pyplot as plt
import numpy as np

colors = plt.cm.viridis(np.linspace(0.05, 0.95, table.shape[1]))
ax = table.plot.barh(stacked=True, color=colors, figsize=(10, 6), width=0.8)
ax.set_title("Films per genre, by MPAA rating")
ax.set_xlabel("Films")
plt.tight_layout()
plt.show()
""",
    "seaborn": PREP
    + """import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="white")
colors = sns.color_palette("viridis", table.shape[1])
table.plot.barh(stacked=True, color=colors, figsize=(10, 6), width=0.8)
plt.title("Films per genre, by MPAA rating")
plt.tight_layout()
plt.savefig("seaborn.png", dpi=150)
""",
    "plotly": PREP
    + """import plotly.express as px

long = table.reset_index().melt(id_vars="Major_Genre", value_name="Films")
fig = px.bar(long, y="Major_Genre", x="Films", color="MPAA_Rating", orientation="h", color_discrete_sequence=px.colors.sequential.Viridis)
fig.update_layout(title="Films per genre, by MPAA rating", template="simple_white")
fig.show()
""",
    "altair": PREP
    + """import altair as alt

long = table.reset_index().melt(id_vars="Major_Genre", value_name="Films")
chart = alt.Chart(long).mark_bar().encode(
    y=alt.Y("Major_Genre:N", sort="-x"), x="Films:Q", color=alt.Color("MPAA_Rating:N", scale=alt.Scale(scheme="viridis"))
).properties(title="Films per genre, by MPAA rating", width=600)
chart.save("altair.png", scale_factor=2)
""",
    "bokeh": PREP
    + """from bokeh.palettes import Viridis256, linear_palette
from bokeh.plotting import figure, show

genres = list(table.index)
ratings = list(table.columns)
p = figure(y_range=genres, height=500, width=800, title="Films per genre, by MPAA rating")
p.hbar_stack(ratings, y="Major_Genre", height=0.8, color=linear_palette(Viridis256, len(ratings)), source=table.reset_index())
show(p)
""",
}


async def main(out: Path, only: list[str]) -> int:
    uv = find_uv()
    if uv is None:
        print("uv was not found; install it first.")
        return 2
    print(f"uv: {uv}\nbrowser for page-to-picture: {find_browser() or 'NONE (Bokeh and Plotly pages need Edge or Chrome)'}\n")
    sandbox = LocalSandbox(uv)
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for name, code in CODE.items():
        if only and name not in only:
            continue
        start = time.perf_counter()
        result = await sandbox.run(code)
        seconds = time.perf_counter() - start
        if result.ok and result.png:
            (out / f"{name}.png").write_bytes(result.png)
            print(f"OK    {name:11s} {seconds:5.1f}s  {len(result.png) // 1024} KB  {result.versions}")
        else:
            failed += 1
            print(f"FAIL  {name:11s} {seconds:5.1f}s  {result.error[-400:]}")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    folder = Path(args[0]) if args else Path("data") / "experiment_smoke"
    raise SystemExit(asyncio.run(main(folder, args[1:])))
