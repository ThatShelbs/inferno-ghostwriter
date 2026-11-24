"""Realistic sample content for every diagram template (data-science topics), for the gallery, tests and demo mode."""

from __future__ import annotations

from typing import Any

SAMPLES: dict[str, dict[str, Any]] = {
    "nested_rings": {
        "template": "nested_rings",
        "items": [
            {"label": "Artificial Intelligence"},
            {"label": "Machine Learning"},
            {"label": "Deep Learning"},
            {"label": "Generative AI"},
            {"label": "Large Language Models"},
            {"label": "Your chatbot"},
        ],
        "highlight": 3,
        "alt": "Nested circles: AI contains machine learning, which contains deep learning, generative AI, LLMs and chatbots.",
    },
    "radial_bars": {
        "template": "radial_bars",
        "items": [
            {"label": "Gradient boosting", "value": 91, "note": "Best recall on the holdout set, and it trains in four minutes."},
            {"label": "Random forest", "value": 86},
            {"label": "Logistic regression", "value": 78},
            {"label": "Naive Bayes", "value": 64},
            {"label": "Rules engine", "value": 52},
        ],
        "unit": "%",
        "center": "Recall",
        "highlight": 0,
        "alt": "Radial bars comparing the recall of five churn models; gradient boosting leads at 91%.",
    },
    "winner_card": {
        "template": "winner_card",
        "options": [
            {"label": "Bar chart", "glyph": "bars"},
            {"label": "Histogram", "glyph": "bars"},
            {"label": "Radial bars", "glyph": "radial", "note": "Five scores at a glance, and people actually stop scrolling."},
            {"label": "Line chart", "glyph": "line"},
            {"label": "Scatter plot", "glyph": "dots"},
        ],
        "winner": 2,
        "alt": "A radial bar chart card wins with a check mark over four greyed-out standard charts.",
    },
    "pipeline": {
        "template": "pipeline",
        "steps": [
            {"label": "Frame the question", "note": "Write the decision the analysis will change."},
            {"label": "Pull the data", "note": "Query the warehouse; log every filter you apply."},
            {"label": "Build features", "note": "Lags, rolling means and one honest holdout."},
            {"label": "Train & validate", "note": "Time-split cross-validation, never random folds."},
            {"label": "Ship & monitor", "note": "Alert on drift before the dashboard goes stale."},
        ],
        "highlight": 3,
        "alt": "Five steps of a forecasting project, from framing the question to monitoring drift.",
    },
    "layer_stack": {
        "template": "layer_stack",
        "layers": [
            {"label": "Dashboards & apps", "note": "Where the business meets the numbers"},
            {"label": "Semantic layer", "note": "One definition of revenue, everywhere"},
            {"label": "Transformation", "note": "Tested SQL models, versioned in git"},
            {"label": "Warehouse", "note": "Cheap storage, elastic compute"},
            {"label": "Ingestion", "note": "Events, CRM and finance feeds land here"},
        ],
        "highlight": 1,
        "alt": "A modern data stack in five layers, from ingestion up to dashboards, with the semantic layer highlighted.",
    },
    "hub_spoke": {
        "template": "hub_spoke",
        "hub": "Customer 360",
        "spokes": [
            {"label": "Finance data", "note": "Invoices and refunds"},
            {"label": "Product events", "note": "Clicks, sessions, feature use"},
            {"label": "Support tickets", "note": "What broke, and how often"},
            {"label": "CRM data", "note": "Deals, owners, stages"},
            {"label": "Marketing", "note": "Campaign touches"},
            {"label": "Surveys", "note": "NPS and free-text answers"},
        ],
        "highlight": 1,
        "alt": "Six data sources feeding a central Customer 360 view.",
    },
    "matrix_2x2": {
        "template": "matrix_2x2",
        "x_axis": {"name": "Effort to build", "low": "Days", "high": "Quarters"},
        "y_axis": {"name": "Business impact", "low": "Nice to have", "high": "Moves revenue"},
        "quadrants": [
            {"label": "Quick wins", "note": "Ship these first; they buy you trust."},
            {"label": "Big bets", "note": "Worth it with a sponsor and a deadline."},
            {"label": "Fill-ins", "note": "Good for a Friday afternoon."},
            {"label": "Money pits", "note": "Politely say no, with a chart."},
        ],
        "points": [
            {"label": "Churn alerts", "x": 0.22, "y": 0.82},
            {"label": "Pricing model", "x": 0.78, "y": 0.88},
            {"label": "Dashboard refresh", "x": 0.18, "y": 0.28},
            {"label": "Custom data lake", "x": 0.84, "y": 0.18},
        ],
        "highlight": 0,
        "alt": "An effort versus impact matrix placing four analytics projects in quick wins, big bets, fill-ins and money pits.",
    },
    "timeline": {
        "template": "timeline",
        "events": [
            {"when": "2012", "label": "AlexNet", "note": "Deep nets win ImageNet by a mile."},
            {"when": "2014", "label": "GANs", "note": "Two networks learn by arguing."},
            {"when": "2017", "label": "Transformers", "note": "Attention is all you need."},
            {"when": "2018", "label": "BERT", "note": "Pre-train once, fine-tune everywhere."},
            {"when": "2020", "label": "GPT-3", "note": "Few-shot prompting goes mainstream."},
            {"when": "2022", "label": "Chat interfaces", "note": "Everyone's parents try AI."},
        ],
        "highlight": 2,
        "alt": "A timeline of deep learning milestones from 2012 to 2022, with transformers highlighted.",
    },
    "venn": {
        "template": "venn",
        "sets": [
            {"label": "Statistics", "note": "Uncertainty, inference, experiments"},
            {"label": "Programming", "note": "Python, SQL, version control"},
            {"label": "Domain sense", "note": "Knowing which question matters"},
        ],
        "overlap": "Data science",
        "alt": "Three overlapping circles, statistics, programming and domain sense, meeting at data science.",
    },
}

__all__ = ["SAMPLES"]
