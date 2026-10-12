"""The small Markdown subset the spec renderer emits (### headings, **bold**, `code`, nested "- " lists) → HTML."""

from __future__ import annotations

import html
import re


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def to_html(markdown: str) -> str:
    out: list[str] = []
    depth = 0  # open <ul> levels
    for line in markdown.splitlines():
        item = re.match(r"^( *)- (.*)$", line)
        level = len(item.group(1)) // 2 + 1 if item else 0
        while depth > level:
            out.append("</ul>")
            depth -= 1
        while depth < level:
            out.append("<ul>")
            depth += 1
        if item:
            out.append(f"<li>{_inline(item.group(2))}</li>")
        elif line.startswith("### "):
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.strip():
            out.append(f"<p>{_inline(line)}</p>")
    out.extend("</ul>" for _ in range(depth))
    return "\n".join(out)
