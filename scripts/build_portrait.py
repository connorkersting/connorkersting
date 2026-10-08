"""Build the animated ASCII-portrait SVGs (dark + light) for the GitHub profile README.

Input: a subject cutout PNG (RGBA, background already transparent).
Output: assets/portrait-dark.svg and assets/portrait-light.svg.

GitHub strips scripts and styles from the README itself, but an SVG shown through
<img> is its own document, so every animation here is CSS @keyframes inside the SVG.
Run from the repo root:
  uv run --with pillow --with numpy --with scikit-image python scripts/build_portrait.py <cutout.png>
"""
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image
from skimage import exposure

# Portrait grid -----------------------------------------------------------------
CROP = (140, 60, 1190, 1460)  # x0, y0, x1, y1 in source pixels: face-forward head + shoulders
COLS = 96
CELL_W, CELL_H = 4.8, 8.8  # px per character cell; 8px monospace ~= 4.8px advance
FONT_SIZE = 8
# Sparse -> dense. Index 0 (space) is reserved for background. Short ramp = less symbol noise.
RAMP = " .,:;i1tfLCG08@"

# Layout -----------------------------------------------------------------------
PAD = 24
GAP = 40
PANEL_W = 370
PANEL_FONT = 13
PANEL_CHAR_W = 7.8  # forced advance for panel text, via textLength
LINE_H = 21

# Timeline (seconds) -------------------------------------------------------------
ROW_START, ROW_STAGGER, ROW_DUR = 0.2, 0.03, 0.5
IDLE_START = 4.0

# Panel content: resume-level facts only (sourced 2026-10-08). Edit freely.
USER = "connor"
NAME = "Connor Kersting"
FIELDS: list[tuple[str, str]] = [
    ("role", "MSBAi '27 · Haslam, UT Knoxville"),
    ("focus", "analytics engineering · AI solutions"),
    ("stack", "R · Shiny · SQL · Python · Tableau"),
    ("shipped", "us-housing-buy-vs-rent"),
    ("", "buy vs. rent across 389 US metros"),
    ("method", "AI-assisted, human-verified"),
]
BLOCKS = ["#0e4429", "#006d32", "#26a641", "#39d353"]  # GitHub contribution greens


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    ink_top: str
    ink_bottom: str
    prompt: str
    path: str
    muted: str
    text: str
    accent: str
    invert: bool  # light theme: dark pixels get the dense characters


# Restrained palette: neutral ink for the portrait, green only as an accent.
DARK = Theme("dark", "#0d1117", "#f0f6fc", "#6e7681", "#7ee787", "#79c0ff",
             "#8b949e", "#e6edf3", "#f0f6fc", invert=False)
LIGHT = Theme("light", "#ffffff", "#1f2328", "#818b98", "#1a7f37", "#0969da",
              "#59636e", "#1f2328", "#1f2328", invert=True)


def ascii_rows(cutout_path: Path, invert: bool) -> list[str]:
    """Map the cutout to characters, one string per row."""
    src = Image.open(cutout_path).convert("RGBA").crop(CROP)
    w, h = src.size
    rows = round(h / w * COLS * CELL_W / CELL_H)
    alpha = np.asarray(src.getchannel("A").resize((COLS, rows), Image.BOX)) / 255.0
    # Adaptive (local) equalization spreads the face's narrow tonal range across the
    # whole ramp, so brows, eyes, nose shadow and beard separate instead of all mapping
    # to the same dense glyphs. Background is filled with the subject mean first so it
    # doesn't skew the local histograms along the silhouette.
    gray = np.asarray(src.convert("L")).astype(float) / 255.0
    full_alpha = np.asarray(src.getchannel("A")) / 255.0
    gray = np.where(full_alpha > 0.5, gray, gray[full_alpha > 0.5].mean())
    eq = exposure.equalize_adapthist(gray, kernel_size=max(gray.shape) // 6, clip_limit=0.03)
    lum = np.asarray(Image.fromarray((eq * 255).astype(np.uint8)).resize((COLS, rows), Image.BOX)) / 255.0

    subject = alpha > 0.5
    lo, hi = np.percentile(lum[subject], [1, 99])
    v = np.clip((lum - lo) / (hi - lo), 0, 1)
    v = np.clip(0.5 + (v - 0.5) * 1.3, 0, 1)  # gentle S: features separate from skin
    if invert:
        v = 1 - v
    levels = len(RAMP) - 1
    idx = 1 + np.round(v * (levels - 1)).astype(int)
    idx = np.where(alpha < 0.35, 0, idx)
    edge = (alpha >= 0.35) & (alpha < 0.6)  # soften the silhouette edge
    idx = np.where(edge, np.maximum(1, (idx * alpha).astype(int)), idx)
    return ["".join(RAMP[i] for i in row) for row in idx]


def build_svg(rows: list[str], t: Theme) -> str:
    pw, ph = COLS * CELL_W, len(rows) * CELL_H
    px, py = PAD, PAD
    width = round(PAD + pw + GAP + PANEL_W + PAD)
    height = round(PAD + ph + PAD)
    reveal_end = ROW_START + (len(rows) - 1) * ROW_STAGGER + ROW_DUR
    glitch_rows = {round(len(rows) * f) for f in (0.33, 0.35, 0.52)}

    out: list[str] = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-labelledby="t d">')
    add(f"<title id=\"t\">{NAME}</title>")
    add(f'<desc id="d">Animated ASCII portrait of {NAME} beside a terminal-style profile card.</desc>')
    add("<defs>")
    add(f'<linearGradient id="ink" gradientUnits="userSpaceOnUse" x1="0" y1="{py}" x2="0" y2="{py + ph}">'
        f'<stop offset="0" stop-color="{t.ink_top}"/><stop offset="1" stop-color="{t.ink_bottom}"/></linearGradient>')
    add(f'<linearGradient id="scan" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{t.ink_top}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{t.ink_top}" stop-opacity=".35"/>'
        f'<stop offset="1" stop-color="{t.ink_top}" stop-opacity="0"/></linearGradient>')
    add(f'<clipPath id="pc"><rect x="{px}" y="{py}" width="{pw}" height="{ph}"/></clipPath>')
    add("</defs>")

    add("<style>")
    add("text{font-family:ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace;white-space:pre}")
    add(f".p{{font-size:{FONT_SIZE}px;fill:url(#ink)}}")
    add(f".k{{font-size:{PANEL_FONT}px}}")
    # Covers travel two extra cells: steps() floors float progress, and a lost final
    # step must not leave the last column hidden.
    add(f".c{{fill:{t.bg};animation:ty {ROW_DUR}s steps({COLS + 2}) forwards}}")
    add(f"@keyframes ty{{to{{transform:translateX({pw + 2 * CELL_W:.1f}px)}}}}")
    # Reveals are short real fades, never zero-length steps (those can stick at 0).
    add(".o{opacity:0;animation:on .3s ease-out forwards}")
    add("@keyframes on{from{opacity:0}to{opacity:1}}")
    add(f".cur{{fill:{t.accent};opacity:0;animation:bl 1.1s steps(1) infinite}}")
    add("@keyframes bl{0%{opacity:1}50%{opacity:0}}")
    add(f".sw{{opacity:0;animation:sw {reveal_end - ROW_START:.2f}s linear {ROW_START}s 1}}")
    add(f"@keyframes sw{{0%{{opacity:1;transform:translateY(0)}}95%{{opacity:1}}100%{{opacity:0;transform:translateY({ph}px)}}}}")
    add(f".id{{opacity:0;animation:id 7s linear {IDLE_START}s infinite}}")
    add(f"@keyframes id{{0%{{opacity:0;transform:translateY(0)}}2%{{opacity:.6}}40%{{opacity:.6}}42%,100%{{opacity:0;transform:translateY({ph}px)}}}}")
    add(f".g{{animation:gl 6s steps(1) {IDLE_START + 1.5}s infinite}}")
    add("@keyframes gl{0%{transform:none}91%{transform:translateX(5px)}93%{transform:translateX(-4px)}95%{transform:translateX(2px)}97%{transform:none}}")
    add(f".pr{{fill:{t.prompt}}}.pa{{fill:{t.path}}}.mu{{fill:{t.muted}}}.tx{{fill:{t.text}}}.ac{{fill:{t.accent}}}")
    add("@media (prefers-reduced-motion:reduce){.c,.sw,.id{display:none}.o{animation:none;opacity:1}.g,.cur{animation:none}.cur{opacity:1}}")
    add("</style>")

    add(f'<rect width="{width}" height="{height}" rx="12" fill="{t.bg}"/>')

    # Portrait rows
    add("<g>")
    for i, row in enumerate(rows):
        y = py + (i + 1) * CELL_H - CELL_H * 0.23
        cls = "p g" if i in glitch_rows else "p"
        add(f'<text class="{cls}" x="{px}" y="{y:.1f}" textLength="{pw}" lengthAdjust="spacing" '
            f'xml:space="preserve">{escape(row)}</text>')
    add("</g>")
    # Typing covers, clipped so they never slide over the panel
    add('<g clip-path="url(#pc)">')
    for i in range(len(rows)):
        y = py + i * CELL_H
        add(f'<rect class="c" x="{px}" y="{y:.1f}" width="{pw + CELL_W}" height="{CELL_H + 0.6}" '
            f'style="animation-delay:{ROW_START + i * ROW_STAGGER:.2f}s"/>')
    add(f'<rect class="sw" x="{px}" y="{py - 14}" width="{pw}" height="28" fill="url(#scan)"/>')
    add(f'<rect class="id" x="{px}" y="{py - 14}" width="{pw}" height="28" fill="url(#scan)"/>')
    add("</g>")

    # Terminal panel
    kx = px + pw + GAP
    n_lines = 2 + 1 + len(FIELDS) + 2  # prompt, name, rule, fields, blank+blocks, prompt
    ky = py + (ph - n_lines * LINE_H) / 2 + LINE_H
    prompt_len = len(f"{USER}@github:~$ ")

    def fixed(n_chars: int) -> str:
        """Pin panel text to an exact advance so the typing covers line up in any font."""
        return f'textLength="{n_chars * PANEL_CHAR_W:.1f}" lengthAdjust="spacing" xml:space="preserve"'

    def prompt(y: float, cmd: str, delay: float) -> None:
        add(f'<text class="k" x="{kx}" y="{y:.1f}" {fixed(prompt_len + len(cmd))}><tspan class="pr">{USER}@github</tspan>'
            f'<tspan class="mu">:</tspan><tspan class="pa">~</tspan><tspan class="mu">$ </tspan>'
            f'<tspan class="tx">{escape(cmd)}</tspan></text>')
        if cmd:
            cx = kx + prompt_len * PANEL_CHAR_W
            cw = len(cmd) * PANEL_CHAR_W
            add(f'<rect x="{cx:.1f}" y="{y - PANEL_FONT:.1f}" width="{cw + PANEL_CHAR_W:.1f}" '
                f'height="{LINE_H - 2}" fill="{t.bg}" style="animation:tc{len(cmd)} .5s steps({len(cmd) + 1}) {delay}s forwards"/>')
            add(f"<style>@keyframes tc{len(cmd)}{{to{{transform:translateX({cw + PANEL_CHAR_W:.1f}px)}}}}</style>")

    def line(y: float, delay: float, body: str, n_chars: int | None = None, size: int | None = None) -> None:
        style = f"animation-delay:{delay:.2f}s" + (f";font-size:{size}px;font-weight:700" if size else "")
        width = f" {fixed(n_chars)}" if n_chars else ' xml:space="preserve"'
        add(f'<text class="k o" x="{kx}" y="{y:.1f}"{width} style="{style}">{body}</text>')

    y = ky
    prompt(y, "whoami", 0.5)
    y += LINE_H + 6
    line(y, 1.15, f'<tspan class="ac">{escape(NAME)}</tspan>', size=20)
    y += LINE_H - 4
    line(y, 1.3, f'<tspan class="mu">{"─" * 30}</tspan>', n_chars=30)
    delay = 1.45
    for key, value in FIELDS:
        y += LINE_H
        line(y, delay, f'<tspan class="pr">{escape(key):<10}</tspan><tspan class="tx">{escape(value)}</tspan>',
             n_chars=10 + len(value))
        delay += 0.15
    y += LINE_H + 2
    for j, color in enumerate(BLOCKS):
        add(f'<rect class="o" x="{kx + j * 22}" y="{y - 12}" width="16" height="16" rx="3" fill="{color}" '
            f'style="animation-delay:{delay + j * 0.08:.2f}s"/>')
    y += LINE_H + 10
    end = delay + 0.5
    add(f'<g class="o" style="animation-delay:{end:.2f}s">')
    prompt(y, "", end)
    add("</g>")
    cur_x = kx + prompt_len * PANEL_CHAR_W
    add(f'<rect class="cur" x="{cur_x:.1f}" y="{y - PANEL_FONT + 1:.1f}" width="{PANEL_CHAR_W:.1f}" '
        f'height="{PANEL_FONT + 2}" style="animation-delay:{end:.2f}s"/>')
    add("</svg>")
    return "\n".join(out)


def main(cutout: str) -> None:
    assets = Path("assets")
    assets.mkdir(exist_ok=True)
    for theme in (DARK, LIGHT):
        rows = ascii_rows(Path(cutout), invert=theme.invert)
        svg = build_svg(rows, theme)
        path = assets / f"portrait-{theme.name}.svg"
        path.write_text(svg, encoding="utf-8")
        print(f"{path}  {len(svg.encode('utf-8')) / 1024:.1f} KB  {len(rows)} rows x {COLS} cols")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: build_portrait.py <cutout.png>")
    main(sys.argv[1])
