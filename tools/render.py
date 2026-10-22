#!/usr/bin/env python3
"""Render recipes/*.yaml into Markdown pages, engineer's-format SVG charts,
and the README index.

    python3 tools/render.py          # write outputs
    python3 tools/render.py --check  # exit 1 if any output is stale
"""

import argparse
import html
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RECIPES = ROOT / "recipes"
README = ROOT / "README.md"
INDEX_START = "<!-- index:start -->"
INDEX_END = "<!-- index:end -->"


class RecipeError(Exception):
    pass


# --- Loading and validation -------------------------------------------------


def load(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RecipeError(f"{path.name}: expected a mapping at the top level")
    for key in ("title", "ingredients", "chart"):
        if key not in data:
            raise RecipeError(f"{path.name}: missing required key '{key}'")
    data["slug"] = path.stem
    validate(data, path.name)
    return data


def as_lines(value):
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def validate(r, name):
    ingredients = {}
    optional = set()
    for group in r["ingredients"]:
        for item in group["items"]:
            for key in ("id", "name", "amount"):
                if key not in item:
                    raise RecipeError(f"{name}: ingredient {item} is missing '{key}'")
            item["amount"] = str(item["amount"])
            if item["id"] in ingredients:
                raise RecipeError(f"{name}: duplicate id '{item['id']}'")
            ingredients[item["id"]] = item
            if group.get("optional"):
                optional.add(item["id"])

    steps = {}
    used = {}
    for step in r["chart"]:
        sid = step.get("id")
        if not sid or "uses" not in step or "do" not in step:
            raise RecipeError(f"{name}: chart step {step} needs 'id', 'uses' and 'do'")
        if sid in ingredients or sid in steps:
            raise RecipeError(f"{name}: duplicate id '{sid}'")
        if not step["uses"]:
            raise RecipeError(f"{name}: step '{sid}' uses nothing")
        for ref in step["uses"]:
            if ref not in ingredients and ref not in steps:
                raise RecipeError(
                    f"{name}: step '{sid}' uses '{ref}', which is not an ingredient "
                    "or an earlier step"
                )
            if ref in used:
                raise RecipeError(
                    f"{name}: '{ref}' is used by both '{used[ref]}' and '{sid}'"
                )
            if ref in optional:
                raise RecipeError(f"{name}: optional ingredient '{ref}' is in the chart")
            used[ref] = sid
        step["lines"] = as_lines(step["do"])
        steps[sid] = step

    roots = [s for s in steps if s not in used]
    if len(roots) != 1:
        raise RecipeError(
            f"{name}: the chart must end in one final step, found {roots or 'none'}"
        )
    missing = [i for i in ingredients if i not in used and i not in optional]
    if missing:
        raise RecipeError(
            f"{name}: ingredients not in the chart (mark their group optional?): "
            + ", ".join(missing)
        )
    r["_ingredients"] = ingredients
    r["_steps"] = steps
    r["_root"] = roots[0]


# --- Engineer's chart layout -------------------------------------------------

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_SIZE = 13
TITLE_SIZE = 15
LINE_H = 17
PAD_X = 8
PAD_Y = 6
ROW_H = LINE_H + 2 * PAD_Y
STEP_WRAP = 260  # max text width in a step column before wrapping

NARROW = set("il.,;:'|!1tfjrI ()[]")
WIDE = set("mwMW@%—")


def text_width(s, size=FONT_SIZE):
    w = 0.0
    for ch in s:
        if ch in NARROW:
            w += 0.32
        elif ch in WIDE:
            w += 0.86
        elif ch.isupper() or ch.isdigit():
            w += 0.64
        else:
            w += 0.54
    return w * size * 1.1  # headroom for wider system fonts


def wrap(line, limit):
    """Wrap to the fewest lines that fit, then even out their lengths."""
    lines = greedy_wrap(line, limit)
    target = text_width(line) / len(lines)
    while target < limit:
        balanced = greedy_wrap(line, target)
        if len(balanced) == len(lines):
            return balanced
        target += FONT_SIZE / 2
    return lines


def greedy_wrap(line, limit):
    words, out, cur = line.split(), [], ""
    for word in words:
        trial = f"{cur} {word}" if cur else word
        if cur and text_width(trial) > limit:
            out.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        out.append(cur)
    return out or [""]


def layout(r):
    """Return rows, step columns and spans for the chart.

    Each ingredient is a row. A step occupies one column and spans exactly the
    rows of everything it uses; an input's cell stretches right until the step
    that consumes it, which is what makes the chart read as a tree.
    """
    ings, steps = r["_ingredients"], r["_steps"]
    rows, span, col = [], {}, {}

    def visit(node):
        if node in ings:
            span[node] = (len(rows), len(rows))
            rows.append(node)
            col[node] = 0
            return
        firsts, lasts = [], []
        for ref in steps[node]["uses"]:
            visit(ref)
            firsts.append(span[ref][0])
            lasts.append(span[ref][1])
        span[node] = (min(firsts), max(lasts))
        col[node] = 1 + max(col[ref] for ref in steps[node]["uses"])

    visit(r["_root"])
    parent = {ref: sid for sid, s in steps.items() for ref in s["uses"]}
    return rows, span, col, parent


def render_svg(r):
    ings, steps = r["_ingredients"], r["_steps"]
    rows, span, col, parent = layout(r)
    ncols = col[r["_root"]]

    # Column widths: [amount, name, step 1, ..., step n]
    amount_w = max(text_width(ings[i]["amount"]) for i in rows) + 2 * PAD_X
    name_w = max(text_width(ings[i]["name"]) for i in rows) + 2 * PAD_X
    wrapped = {
        sid: [w for line in s["lines"] for w in wrap(line, STEP_WRAP)]
        for sid, s in steps.items()
    }
    step_w = [0.0] * (ncols + 1)
    for sid in steps:
        need = max(text_width(line) for line in wrapped[sid]) + 2 * PAD_X
        step_w[col[sid]] = max(step_w[col[sid]], need)
    # A wider neighbour in the same column may leave room to unwrap.
    for sid, s in steps.items():
        roomy = [w for line in s["lines"] for w in greedy_wrap(line, step_w[col[sid]] - 2 * PAD_X)]
        if len(roomy) < len(wrapped[sid]):
            wrapped[sid] = roomy

    # Row heights grow until every step's text fits in the rows it spans.
    heights = [ROW_H] * len(rows)
    for sid in sorted(steps, key=lambda s: col[s]):
        first, last = span[sid]
        need = len(wrapped[sid]) * LINE_H + 2 * PAD_Y
        have = sum(heights[first : last + 1])
        if need > have:
            heights[last] += need - have

    title_h = TITLE_SIZE + 2 * PAD_Y + 4
    x_step = [0.0] * (ncols + 2)
    x_step[1] = amount_w + name_w
    for c in range(1, ncols + 1):
        x_step[c + 1] = x_step[c] + step_w[c]
    width = x_step[ncols + 1]
    y_row = [title_h]
    for h in heights:
        y_row.append(y_row[-1] + h)
    height = y_row[-1]

    def end_x(node):
        # A cell stretches to the column of whatever consumes it.
        return x_step[col[parent[node]]] if node in parent else width

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
        f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'font-family="{FONT}" font-size="{FONT_SIZE}">',
        f"<title>{esc(r['title'])}: engineer's chart</title>",
        "<style>",
        ".bg{fill:#ffffff}.title{fill:#2c2c2a;font-weight:600}",
        ".mat{fill:#f7f6f1;stroke:#d3d1c7}.act{fill:#fbf3e6;stroke:#e6b873}",
        ".edge{fill:none;stroke:#8a877c;stroke-width:1.5}",
        "text{fill:#2c2c2a}.amt{fill:#5f5e5a}",
        "@media (prefers-color-scheme: dark){",
        ".bg{fill:#1d1d1b}.title{fill:#ecebe6}",
        ".mat{fill:#2a2a27;stroke:#4a4944}.act{fill:#3a2f1e;stroke:#9a7436}",
        ".edge{stroke:#8a877c}text{fill:#ecebe6}.amt{fill:#b4b2a9}}",
        "</style>",
        f'<rect class="bg" width="{width:.0f}" height="{height:.0f}"/>',
        f'<text class="title" x="{PAD_X}" y="{title_h / 2:.1f}" '
        f'dominant-baseline="central" font-size="{TITLE_SIZE}">{esc(r["title"])}</text>',
    ]

    def cell(cls, x0, y0, x1, y1, lines, text_cls=None):
        out.append(
            f'<rect class="{cls}" x="{x0:.1f}" y="{y0:.1f}" '
            f'width="{x1 - x0:.1f}" height="{y1 - y0:.1f}"/>'
        )
        top = (y0 + y1) / 2 - (len(lines) - 1) * LINE_H / 2
        attr = f' class="{text_cls}"' if text_cls else ""
        for n, line in enumerate(lines):
            out.append(
                f'<text{attr} x="{x0 + PAD_X:.1f}" y="{top + n * LINE_H:.1f}" '
                f'dominant-baseline="central">{esc(line)}</text>'
            )

    for n, iid in enumerate(rows):
        y0, y1 = y_row[n], y_row[n + 1]
        cell("mat", 0, y0, amount_w, y1, [ings[iid]["amount"]], "amt")
        cell("mat", amount_w, y0, end_x(iid), y1, [ings[iid]["name"]])
    for sid in steps:
        first, last = span[sid]
        cell("act", x_step[col[sid]], y_row[first], end_x(sid), y_row[last + 1], wrapped[sid])

    out.append(
        f'<rect class="edge" x="0.75" y="0.75" width="{width - 1.5:.1f}" '
        f'height="{height - 1.5:.1f}"/>'
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def esc(s):
    return html.escape(str(s), quote=True)


# --- Markdown ----------------------------------------------------------------


def render_markdown(r):
    slug = r["slug"]
    md = [
        f"<!-- Generated from {slug}.yaml by tools/render.py. Edit the YAML, not this file. -->",
        "",
        f"# {r['title']}",
        "",
    ]
    if r.get("summary"):
        md += [r["summary"], ""]
    if r.get("facts"):
        md += [f"- **{k}:** {v}" for k, v in r["facts"].items()] + [""]

    md += [
        "## At a glance",
        "",
        f"![Engineer's chart for {r['title']}]({slug}.svg)",
        "",
        "Read left to right. Each shaded box is a step that combines "
        "everything to its left.",
        "",
        "## Ingredients",
        "",
    ]
    for group in r["ingredients"]:
        md += [f"### {group['group']}", "", "| Ingredient | Amount |", "| --- | --- |"]
        for item in group["items"]:
            amount = item["amount"]
            if item.get("note"):
                amount += f" — {item['note']}"
            md.append(f"| {item['name']} | {amount} |")
        md.append("")

    if r.get("method"):
        md += ["## Method", ""]
        for n, step in enumerate(r["method"], 1):
            title = f"**{step['title']}** " if step.get("title") else ""
            md.append(f"{n}. {title}{step['text']}")
        md.append("")

    if r.get("notes"):
        md += ["## Notes", ""] + [f"- {n}" for n in r["notes"]] + [""]
    return "\n".join(md)


def render_index(recipes, readme):
    if INDEX_START not in readme or INDEX_END not in readme:
        raise RecipeError(f"README.md needs {INDEX_START} and {INDEX_END} markers")
    rows = ["| Recipe | Notes |", "| --- | --- |"]
    for r in sorted(recipes, key=lambda r: r["title"].lower()):
        note = r.get("index_note") or r.get("summary", "")
        rows.append(f"| [{r['title']}](recipes/{r['slug']}.md) | {note} |")
    head, rest = readme.split(INDEX_START, 1)
    _, tail = rest.split(INDEX_END, 1)
    return f"{head}{INDEX_START}\n" + "\n".join(rows) + f"\n{INDEX_END}{tail}"


# --- Entry point ---------------------------------------------------------------


def outputs(recipes_dir=RECIPES, readme_path=README):
    recipes = [load(p) for p in sorted(recipes_dir.glob("*.yaml"))]
    files = {}
    for r in recipes:
        files[recipes_dir / f"{r['slug']}.md"] = render_markdown(r)
        files[recipes_dir / f"{r['slug']}.svg"] = render_svg(r)
    files[readme_path] = render_index(recipes, readme_path.read_text(encoding="utf-8"))
    return files


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if outputs are stale")
    args = ap.parse_args()
    try:
        files = outputs()
    except RecipeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    stale = []
    for path, content in files.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        stale.append(path.relative_to(ROOT))
        if not args.check:
            path.write_text(content, encoding="utf-8")
    for p in stale:
        print(f"{'stale' if args.check else 'wrote'}: {p}")
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
