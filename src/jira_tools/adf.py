"""Markdown turned into the Atlassian Document Format (ADF), which Jira Cloud's API takes for an
issue's description and comments, and ADF read back as Markdown (see to_markdown).

It covers what an issue's description needs: paragraphs, headings, bullet and numbered lists,
fenced code blocks, and inline code, bold and links. Lists are flat: an indented line continues
the item above it. Anything else is kept as text.
"""

import re
from datetime import UTC, datetime

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE = re.compile(r"^(`{3,})\s*([^`\s]*)\s*$")
BULLET = re.compile(r"^[-*+]\s+(.*)$")
NUMBERED = re.compile(r"^\d+[.)]\s+(.*)$")
INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)\s]+)\)")


def from_markdown(markdown: str) -> dict:
    """The ADF document for markdown."""
    return {"type": "doc", "version": 1, "content": _blocks(markdown.splitlines())}


def _blocks(lines: list[str]) -> list[dict]:
    blocks: list[dict] = []
    paragraph: list[str] = []
    i = 0

    def end_paragraph() -> None:
        if paragraph:
            blocks.append({"type": "paragraph", "content": _inline(" ".join(paragraph))})
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if fence := FENCE.match(stripped):
            end_paragraph()
            end = next(
                (j for j in range(i + 1, len(lines)) if _closes(lines[j].strip(), fence[1])), None
            )
            body = lines[i + 1 : end]
            blocks.append(_code_block(fence[2], "\n".join(body)))
            i = len(lines) if end is None else end + 1
        elif not stripped:
            end_paragraph()
            i += 1
        elif heading := HEADING.match(stripped):
            end_paragraph()
            level = len(heading[1])
            blocks.append(
                {"type": "heading", "attrs": {"level": level}, "content": _inline(heading[2])}
            )
            i += 1
        elif BULLET.match(stripped) or NUMBERED.match(stripped):
            end_paragraph()
            kind = BULLET if BULLET.match(stripped) else NUMBERED
            items, i = _list_items(lines, i, kind)
            list_type = "bulletList" if kind is BULLET else "orderedList"
            blocks.append({"type": list_type, "content": items})
        else:
            paragraph.append(stripped)
            i += 1
    end_paragraph()
    return blocks


def _list_items(lines: list[str], i: int, kind: re.Pattern[str]) -> tuple[list[dict], int]:
    """The items of the list starting at line i whose markers match kind, and the line after it.
    An indented line that isn't an item continues the one above."""
    texts: list[str] = []
    while i < len(lines):
        line = lines[i]
        if item := kind.match(line.strip()):
            texts.append(item[1].strip())
        elif texts and line[:1].isspace() and line.strip():
            texts[-1] += " " + line.strip()
        else:
            break
        i += 1
    items = [
        {"type": "listItem", "content": [{"type": "paragraph", "content": _inline(text)}]}
        for text in texts
    ]
    return items, i


def _closes(line: str, opening: str) -> bool:
    """Whether line closes the fence opened by opening: backticks alone, at least as many."""
    return len(line) >= len(opening) and set(line) == {"`"}


def _code_block(language: str, body: str) -> dict:
    block: dict = {"type": "codeBlock"}
    if language:
        block["attrs"] = {"language": language}
    if body:
        block["content"] = [{"type": "text", "text": body}]
    return block


def _inline(text: str) -> list[dict]:
    """Text nodes for text, marked where it has inline code, bold or a link."""
    nodes: list[dict] = []
    position = 0
    for match in INLINE.finditer(text):
        if match.start() > position:
            nodes.append(_text(text[position : match.start()]))
        code, bold, label, href = match.groups()
        if code is not None:
            nodes.append(_text(code, {"type": "code"}))
        elif bold is not None:
            nodes.append(_text(bold, {"type": "strong"}))
        else:
            nodes.append(_text(label, {"type": "link", "attrs": {"href": href}}))
        position = match.end()
    if position < len(text):
        nodes.append(_text(text[position:]))
    return nodes


def _text(value: str, *marks: dict) -> dict:
    node: dict = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def to_markdown(doc: dict, heading_offset: int = 0) -> str:
    """Markdown for an ADF document, such as an issue's description or a comment.

    It covers what Jira's editor makes: what from_markdown writes, and nested and task lists,
    quotes, panels, tables, expands, rules, mentions, emoji, dates, statuses and links to pages.
    An embedded file is named, as [attachment: <name>]. A node it doesn't know keeps its text.
    heading_offset moves every heading down that many levels, to sit under a section.
    """
    return _md_blocks(doc.get("content", []), heading_offset, "\n\n")


def _md_blocks(nodes: list[dict], offset: int, between: str) -> str:
    return between.join(text for node in nodes if (text := _md_block(node, offset)))


def _md_block(node: dict, offset: int) -> str:
    content = node.get("content", [])
    attrs = node.get("attrs", {})
    match node.get("type"):
        case "paragraph":
            return _md_inline(content)
        case "heading":
            return "#" * min(6, attrs.get("level", 1) + offset) + " " + _md_inline(content)
        case "bulletList":
            return _md_list(content, lambda n: "- ", offset)
        case "orderedList":
            start = attrs.get("order", 1)
            return _md_list(content, lambda n: f"{start + n}. ", offset)
        case "taskList" | "decisionList":
            return _md_list(content, lambda n: "- ", offset)
        case "codeBlock":
            body = "".join(child.get("text", "") for child in content)
            fence = "`" * max([3, *(len(run) + 1 for run in re.findall("`+", body))])
            return f"{fence}{attrs.get('language', '')}\n{body}\n{fence}"
        case "blockquote":
            return _quoted(_md_blocks(content, offset, "\n\n"))
        case "panel":
            label = f"**{attrs.get('panelType', 'info').capitalize()}:** "
            return _quoted(label + _md_blocks(content, offset, "\n\n"))
        case "rule":
            return "---"
        case "table":
            return _md_table(content, offset)
        case "expand" | "nestedExpand":
            body = _md_blocks(content, offset, "\n\n")
            return "\n\n".join(part for part in (f"**{attrs.get('title', '')}**", body) if part)
        case "mediaSingle" | "mediaGroup":
            return " ".join(_md_inline_node(child) for child in content)
        case "blockCard" | "embedCard":
            return f"<{attrs.get('url', '')}>"
        case _ if any(child.get("type") != "text" and "content" in child for child in content):
            return _md_blocks(content, offset, "\n\n")
        case _:
            return _md_inline(content)


def _md_list(items: list[dict], marker, offset: int) -> str:
    """Each item on its own line after its marker, a following line indented to sit under it."""
    lines: list[str] = []
    for n, item in enumerate(items):
        prefix = marker(n)
        if item.get("type") in ("taskItem", "decisionItem"):
            done = item.get("attrs", {}).get("state") in ("DONE", "DECIDED")
            prefix += "[x] " if done else "[ ] "
            body = _md_inline(item.get("content", []))
        else:
            body = _md_blocks(item.get("content", []), offset, "\n")
        first, *rest = body.split("\n")
        lines.append(prefix + first)
        lines += [" " * len(marker(n)) + line if line else "" for line in rest]
    return "\n".join(lines)


def _md_table(rows: list[dict], offset: int) -> str:
    """A Markdown table, its first row the header."""
    cells = [
        [
            _md_blocks(cell.get("content", []), offset, " ").replace("\n", " ").replace("|", "\\|")
            for cell in row.get("content", [])
        ]
        for row in rows
    ]
    if not cells:
        return ""
    width = max(len(row) for row in cells)
    lines = ["| " + " | ".join(row + [""] * (width - len(row))) + " |" for row in cells]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def _quoted(text: str) -> str:
    return "\n".join(f"> {line}" if line else ">" for line in text.split("\n"))


def _md_inline(nodes: list[dict]) -> str:
    return "".join(_md_inline_node(node) for node in nodes)


def _md_inline_node(node: dict) -> str:
    attrs = node.get("attrs", {})
    match node.get("type"):
        case "text":
            return _marked(node.get("text", ""), node.get("marks", []))
        case "hardBreak":
            return "\n"
        case "mention":
            name = attrs.get("text", "")
            return name if name.startswith("@") else f"@{name}"
        case "emoji":
            return attrs.get("text") or attrs.get("shortName", "")
        case "inlineCard":
            return f"<{attrs.get('url', '')}>"
        case "status":
            return f"[{attrs.get('text', '')}]"
        case "date":
            moment = datetime.fromtimestamp(int(attrs.get("timestamp", 0)) / 1000, UTC)
            return moment.date().isoformat()
        case "media" | "mediaInline":
            return f"[attachment: {attrs.get('alt') or attrs.get('id') or 'file'}]"
        case _:
            return _md_inline(node.get("content", [])) or attrs.get("text", "")


def _marked(text: str, marks: list[dict]) -> str:
    """text with its marks: code innermost, then bold, italic and strike, a link outermost."""
    kinds = {mark.get("type"): mark for mark in marks}
    if "code" in kinds:
        text = f"`{text}`"
    if "strong" in kinds:
        text = f"**{text}**"
    if "em" in kinds:
        text = f"*{text}*"
    if "strike" in kinds:
        text = f"~~{text}~~"
    if link := kinds.get("link"):
        text = f"[{text}]({link.get('attrs', {}).get('href', '')})"
    return text
