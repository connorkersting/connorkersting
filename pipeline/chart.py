"""Render the price-to-rent dumbbell chart as a self-contained SVG (dark or light theme).

Matches the profile's restrained palette: neutral text, one Tennessee Orange accent for the current
month, a hollow grey ring for the same month a year earlier. The title states the finding.
"""
from __future__ import annotations

import math
from datetime import date
from xml.sax.saxutils import escape

import pandas as pd

# Tennessee Orange for the current month (#FF8200 on dark; burnt #B85A00 on white for contrast).
THEMES: dict[str, dict[str, str]] = {
    "dark": {"bg": "#0d1117", "text": "#e6edf3", "muted": "#8b949e", "grid": "#21262d",
             "line": "#30363d", "now": "#ff8200", "ago": "#6e7681"},
    "light": {"bg": "#ffffff", "text": "#1f2328", "muted": "#59636e", "grid": "#eaeef2",
              "line": "#d0d7de", "now": "#b85a00", "ago": "#818b98"},
}
WIDTH = 860
LEFT, RIGHT = 230, 70  # label column and value column
TOP = 112
ROW_H = 22
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def short_metro(name: str) -> str:
    """'Miami-Fort Lauderdale, FL' -> 'Miami, FL' keeps the label column readable."""
    city, _, state = name.partition(", ")
    return f"{city.split('-')[0].split('/')[0]}, {state}" if state else name


def render_chart(table: pd.DataFrame, month: date, theme: str) -> str:
    c = THEMES[theme]
    n = len(table)
    height = TOP + n * ROW_H + 48
    values = pd.concat([table["price_to_rent"], table["price_to_rent_year_ago"]]).dropna()
    lo = math.floor(values.min() / 5) * 5
    hi = math.ceil(values.max() / 5) * 5
    plot_w = WIDTH - LEFT - RIGHT

    def x(v: float) -> float:
        return LEFT + (v - lo) / (hi - lo) * plot_w

    top_row, bottom_row = table.iloc[0], table.iloc[-1]
    title = (f"Homes cost {top_row['price_to_rent']:.0f}x a year's rent in {short_metro(top_row['metro'])}, "
             f"{bottom_row['price_to_rent']:.0f}x in {short_metro(bottom_row['metro'])}")
    ago_label = f"{date(month.year - 1, month.month, 1):%b %Y}"

    out: list[str] = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" '
        f'height="{height}" role="img" aria-labelledby="ct cd">')
    add(f'<title id="ct">{escape(title)}</title>')
    add(f'<desc id="cd">Price-to-rent ratio (typical home value divided by 12 months of typical rent) '
        f'for the {n} largest US metros, {month:%B %Y} versus {ago_label}. Source: Zillow Research.</desc>')
    add("<style>")
    add(f"text{{font-family:{FONT};font-variant-numeric:tabular-nums}}")
    add(".r{opacity:0;animation:in .45s ease-out forwards}")
    add("@keyframes in{from{opacity:0;transform:translateX(-6px)}to{opacity:1;transform:none}}")
    add("@media (prefers-reduced-motion:reduce){.r{animation:none;opacity:1}}")
    add("</style>")
    add(f'<rect width="{WIDTH}" height="{height}" rx="12" fill="{c["bg"]}"/>')
    add(f'<text x="24" y="40" font-size="19" font-weight="600" fill="{c["text"]}">{escape(title)}</text>')
    add(f'<text x="24" y="64" font-size="13" fill="{c["muted"]}">Price-to-rent ratio: typical home value ÷ '
        f'12 months of typical rent. Higher means renting is relatively cheaper.</text>')
    # Legend, directly labeled
    ly = 90
    add(f'<circle cx="30" cy="{ly - 4}" r="5" fill="{c["now"]}"/>')
    add(f'<text x="42" y="{ly}" font-size="12" fill="{c["text"]}">{month:%b %Y}</text>')
    add(f'<circle cx="112" cy="{ly - 4}" r="4.5" fill="none" stroke="{c["ago"]}" stroke-width="1.6"/>')
    add(f'<text x="124" y="{ly}" font-size="12" fill="{c["muted"]}">{ago_label}</text>')
    # Gridlines every 5
    for v in range(lo, hi + 1, 5):
        gx = x(v)
        add(f'<line x1="{gx:.1f}" y1="{TOP - 8}" x2="{gx:.1f}" y2="{TOP + n * ROW_H - 6}" stroke="{c["grid"]}"/>')
        add(f'<text x="{gx:.1f}" y="{TOP - 14}" font-size="11" fill="{c["muted"]}" text-anchor="middle">{v}</text>')
    # Rows
    for i, row in enumerate(table.itertuples(index=False)):
        cy = TOP + i * ROW_H + 6
        now, ago = row.price_to_rent, row.price_to_rent_year_ago
        add(f'<g class="r" style="animation-delay:{0.15 + i * 0.04:.2f}s">')
        add(f'<text x="{LEFT - 14}" y="{cy + 4}" font-size="12.5" fill="{c["text"]}" text-anchor="end">'
            f'{escape(short_metro(row.metro))}</text>')
        if pd.notna(ago):
            add(f'<line x1="{x(ago):.1f}" y1="{cy}" x2="{x(now):.1f}" y2="{cy}" stroke="{c["line"]}" stroke-width="2"/>')
            add(f'<circle cx="{x(ago):.1f}" cy="{cy}" r="4.5" fill="{c["bg"]}" stroke="{c["ago"]}" stroke-width="1.6"/>')
        add(f'<circle cx="{x(now):.1f}" cy="{cy}" r="5" fill="{c["now"]}"/>')
        add(f'<text x="{WIDTH - RIGHT + 16}" y="{cy + 4}" font-size="12.5" fill="{c["text"]}">{now:.1f}</text>')
        add("</g>")
    fy = TOP + n * ROW_H + 26
    add(f'<text x="24" y="{fy}" font-size="11" fill="{c["muted"]}">Source: Zillow Research (ZHVI, ZORI), '
        f'{month:%B %Y}. Rebuilt monthly by a GitHub Action with schema and row-count checks.</text>')
    add("</svg>")
    return "\n".join(out) + "\n"
