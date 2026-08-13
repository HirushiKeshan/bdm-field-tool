"""
A small inline-SVG sparkline for the 6-month billing trend on the Counter
Conversation screen. Deliberately not a generic chart widget: it has to
keep the three-way null distinction from docs/data-notes.md visible in
the chart itself, not just in a text caption --

  - a real billed month  -> solid navy dot, connected by a line
  - an explicit zero bill -> solid pink/accent dot, still on the baseline
  - no record that month -> hollow dashed circle, breaks the line

A generic line-chart widget (st.line_chart, a stray fillna(0)) would
collapse "no record" into "zero" and silently misrepresent the data --
exactly what docs/data-notes.md's null-handling rules forbid.
"""
from typing import Optional

NAVY = "#0B2D6B"
ACCENT = "#D6266E"
GREY = "#b6bcc9"


def render_trend_sparkline(trend: list, width: int = 320, height: int = 78) -> str:
    """trend: [{"month": "YYYY-MM", "value": float|None, "has_record": bool}, ...]
    Returns a standalone <svg> string, safe to pass to st.markdown(unsafe_allow_html=True)."""
    n = len(trend)
    if n == 0:
        return "<svg></svg>"

    pad_x, pad_top, pad_bottom = 10, 10, 16
    plot_w = width - 2 * pad_x
    plot_h = height - pad_top - pad_bottom
    xs = [pad_x + i * (plot_w / (n - 1)) for i in range(n)] if n > 1 else [width / 2]

    positive_values = [t["value"] for t in trend if t.get("has_record") and t.get("value") and t["value"] > 0]
    max_val = max(positive_values) if positive_values else 1
    baseline_y = pad_top + plot_h

    def y_for(value: Optional[float]) -> float:
        if not value:
            return baseline_y
        return pad_top + plot_h - (value / max_val) * plot_h

    segments, points, labels = [], [], []
    prev_has_record = False
    prev_x = prev_y = None

    for i, t in enumerate(trend):
        x = xs[i]
        has_record = bool(t.get("has_record"))
        value = t.get("value")
        if has_record:
            y = y_for(value)
            color = ACCENT if not value else NAVY
            points.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" />')
            if prev_has_record and prev_x is not None:
                segments.append(
                    f'<line x1="{prev_x:.1f}" y1="{prev_y:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                    f'stroke="{NAVY}" stroke-width="2" stroke-linecap="round" />'
                )
            prev_x, prev_y, prev_has_record = x, y, True
        else:
            points.append(
                f'<circle cx="{x:.1f}" cy="{baseline_y:.1f}" r="3.5" fill="none" '
                f'stroke="{GREY}" stroke-width="1.5" stroke-dasharray="2,2" />'
            )
            prev_has_record = False

        labels.append(
            f'<text x="{x:.1f}" y="{height - 3}" font-size="9" fill="#98a0b3" '
            f'text-anchor="middle" font-family="sans-serif">{t["month"][-2:]}</text>'
        )

    svg = (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<line x1="{pad_x}" y1="{baseline_y:.1f}" x2="{width - pad_x}" y2="{baseline_y:.1f}" '
        f'stroke="#eceef2" stroke-width="1" />'
        + "".join(segments) + "".join(points) + "".join(labels) +
        "</svg>"
    )
    return svg
