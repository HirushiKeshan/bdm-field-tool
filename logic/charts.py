"""
An interactive Plotly line chart for the 6-month billing trend on the
Counter Conversation screen. Not decoration -- it has to keep the
three-way null distinction from docs/data-notes.md visible and hoverable,
not just present in a static image:

  - a real billed month  -> solid navy point, connected by a line
  - an explicit zero bill -> solid accent-pink point, still connected
    (it's a real record, just a bad month)
  - no record that month -> hollow grey marker sitting at the baseline,
    with a genuine gap in the line on either side (Plotly's
    connectgaps=False), and its own "no record" hover label

A generic chart built by feeding raw values straight into st.line_chart
(or any fillna(0)) would collapse "no record" into "zero" -- exactly what
docs/data-notes.md's null-handling rules forbid.
"""
from typing import Optional

import plotly.graph_objects as go

from logic.scoring import format_inr

NAVY = "#0B2D6B"
ACCENT = "#D6266E"
GREY = "#b6bcc9"
LOW = "#D6266E"    # needs attention
MID = "#F5821F"
HIGH = "#1EBFAE"   # solid


def build_trend_figure(trend: list) -> go.Figure:
    """trend: [{"month": "YYYY-MM", "value": float|None, "has_record": bool}, ...]"""
    x = [t["month"] for t in trend]
    y_line, marker_colors, hover_text = [], [], []
    no_record_x, no_record_hover = [], []

    for t in trend:
        if t.get("has_record"):
            value = t.get("value") or 0
            y_line.append(value)
            if value == 0:
                marker_colors.append(ACCENT)
                hover_text.append(f"{t['month']}: ₹0 -- billed nothing")
            else:
                marker_colors.append(NAVY)
                hover_text.append(f"{t['month']}: {format_inr(value)}")
        else:
            y_line.append(None)  # a real gap -- connectgaps=False breaks the line here
            marker_colors.append(GREY)
            hover_text.append(f"{t['month']}: no record")
            no_record_x.append(t["month"])
            no_record_hover.append(f"{t['month']}: no record")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y_line, mode="lines+markers",
        line=dict(color=NAVY, width=2, shape="spline", smoothing=0.3),
        marker=dict(color=marker_colors, size=10, line=dict(width=1, color="white")),
        hovertext=hover_text, hoverinfo="text",
        connectgaps=False,
        showlegend=False,
    ))
    if no_record_x:
        # A no-record month has no y-value on the line trace above (by
        # design, to keep the gap real) -- overlay a hollow marker at the
        # baseline just so it's not simply invisible on the chart.
        fig.add_trace(go.Scatter(
            x=no_record_x, y=[0] * len(no_record_x), mode="markers",
            marker=dict(symbol="circle-open", color=GREY, size=10, line=dict(width=2, color=GREY)),
            hovertext=no_record_hover, hoverinfo="text",
            showlegend=False,
        ))

    fig.update_layout(
        height=190,
        margin=dict(l=8, r=8, t=8, b=8),
        xaxis=dict(showgrid=False, tickfont=dict(size=11, color="#8892a6")),
        yaxis=dict(visible=False, rangemode="tozero"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="closest",
        dragmode=False,
    )
    return fig


_SORT_KEYS = {
    "lowest": lambda r: r["pct_to_valuable_outlets"],
    "highest": lambda r: -r["pct_to_valuable_outlets"],
    "az": lambda r: r["bdm_name"],
}


def build_time_allocation_figure(alloc: list, sort_by: str = "lowest", highlight_bdm_code: Optional[str] = None) -> go.Figure:
    """alloc: [{"bdm_code", "bdm_name", "territory", "total_visits", "pct_to_valuable_outlets"}, ...]
    One horizontal bar per BDM instead of 12 stacked st.progress rows --
    same numbers, scannable in one glance. Color bands (not a continuous
    scale) so a manager can spot who needs attention without reading
    every label. highlight_bdm_code outlines one bar (e.g. from the
    Insights "View for" filter) without hiding the rest -- this section
    is inherently a comparison, so filtering it down to one bar would
    remove the context that makes the number meaningful."""
    rows = sorted(alloc, key=_SORT_KEYS.get(sort_by, _SORT_KEYS["lowest"]))
    labels = [f'{r["bdm_name"]} ({r["territory"]})' for r in rows]
    values = [r["pct_to_valuable_outlets"] for r in rows]
    hover = [f'{r["bdm_name"]} ({r["territory"]}): {r["pct_to_valuable_outlets"]}% of '
             f'{r["total_visits"]} visits to outlets that matter' for r in rows]
    colors = [LOW if v < 30 else MID if v < 45 else HIGH for v in values]
    is_highlighted = [highlight_bdm_code is not None and r.get("bdm_code") == highlight_bdm_code for r in rows]
    line_colors = [NAVY if h else "rgba(0,0,0,0)" for h in is_highlighted]
    line_widths = [3 if h else 0 for h in is_highlighted]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=colors, line=dict(color=line_colors, width=line_widths)),
        hovertext=hover, hoverinfo="text",
    ))
    fig.update_layout(
        height=max(220, 34 * len(rows)),
        margin=dict(l=8, r=8, t=8, b=8),
        xaxis=dict(range=[0, 100], ticksuffix="%", showgrid=True, gridcolor="rgba(0,0,0,0.06)"),
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def build_confidence_mix_figure(mix: dict) -> go.Figure:
    """mix: {"Verified": n, "Partial": n, "Unverified": n} (any subset)."""
    order = ["Verified", "Partial", "Unverified"]
    colors = {"Verified": HIGH, "Partial": MID, "Unverified": GREY}
    keys = [k for k in order if k in mix] + [k for k in mix if k not in order]
    values = [mix[k] for k in keys]

    fig = go.Figure(go.Bar(
        x=values, y=keys, orientation="h",
        marker=dict(color=[colors.get(k, GREY) for k in keys]),
        text=values, textposition="outside",
    ))
    fig.update_layout(
        height=max(140, 44 * len(keys)),
        margin=dict(l=8, r=8, t=8, b=8),
        xaxis=dict(visible=False),
        yaxis=dict(autorange="reversed"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig


def build_anomaly_breakdown_figure(breakdown: dict) -> go.Figure:
    """breakdown: {"reason label": count, ...}"""
    items = sorted(breakdown.items(), key=lambda x: x[1])
    labels = [k for k, _ in items]
    values = [v for _, v in items]

    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker=dict(color=ACCENT),
        text=values, textposition="outside",
    ))
    fig.update_layout(
        height=max(140, 44 * len(labels)),
        margin=dict(l=8, r=8, t=8, b=8),
        xaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    return fig
