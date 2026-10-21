"""Markdown, as Claude writes an issue's description, turned into the Atlassian Document Format
that Jira Cloud's API takes; and ADF read back as Markdown."""

from jira_tools.adf import from_markdown, to_markdown


def doc(*content: dict) -> dict:
    return {"type": "doc", "version": 1, "content": list(content)}


def text(value: str, *marks: dict) -> dict:
    node = {"type": "text", "text": value}
    if marks:
        node["marks"] = list(marks)
    return node


def paragraph(*content: dict) -> dict:
    return {"type": "paragraph", "content": list(content)}


def item(value: str) -> dict:
    return {"type": "listItem", "content": [paragraph(text(value))]}


def test_an_empty_description_is_an_empty_document():
    assert from_markdown("") == doc()
    assert from_markdown("\n  \n") == doc()


def test_lines_together_form_one_paragraph_and_a_blank_line_starts_another():
    assert from_markdown("One\ntwo\n\nThree") == doc(
        paragraph(text("One two")), paragraph(text("Three"))
    )


def test_a_heading_keeps_its_level():
    assert from_markdown("## Why") == doc(
        {"type": "heading", "attrs": {"level": 2}, "content": [text("Why")]}
    )


def test_lines_starting_with_a_dash_star_or_plus_make_one_bullet_list():
    assert from_markdown("- a\n* b\n+ c") == doc(
        {"type": "bulletList", "content": [item("a"), item("b"), item("c")]}
    )


def test_numbered_lines_make_an_ordered_list():
    assert from_markdown("1. a\n2) b") == doc(
        {"type": "orderedList", "content": [item("a"), item("b")]}
    )


def test_an_indented_line_continues_the_list_item_above_it():
    assert from_markdown("- a\n  more\n- b") == doc(
        {"type": "bulletList", "content": [item("a more"), item("b")]}
    )


def test_a_list_can_follow_a_paragraph_without_a_blank_line():
    assert from_markdown("Steps:\n- a") == doc(
        paragraph(text("Steps:")), {"type": "bulletList", "content": [item("a")]}
    )


def test_a_fenced_block_is_a_code_block_kept_exactly_with_its_language():
    assert from_markdown("```php\n$a = 1;\n\n  $b = **2**;\n```") == doc(
        {
            "type": "codeBlock",
            "attrs": {"language": "php"},
            "content": [text("$a = 1;\n\n  $b = **2**;")],
        }
    )


def test_a_fenced_block_without_a_language_or_lines_has_neither():
    assert from_markdown("```\n```") == doc({"type": "codeBlock"})


def test_a_fence_left_open_runs_to_the_end():
    assert from_markdown("```\nx") == doc({"type": "codeBlock", "content": [text("x")]})


def test_a_longer_fence_ends_only_at_a_fence_at_least_as_long():
    assert from_markdown("````\n```\n## Done when\n```\n````\nAfter") == doc(
        {"type": "codeBlock", "content": [text("```\n## Done when\n```")]},
        paragraph(text("After")),
    )


def test_inline_code_bold_and_links_are_marked():
    assert from_markdown("Run `make` **now**, see [the docs](https://x.example/a).") == doc(
        paragraph(
            text("Run "),
            text("make", {"type": "code"}),
            text(" "),
            text("now", {"type": "strong"}),
            text(", see "),
            text("the docs", {"type": "link", "attrs": {"href": "https://x.example/a"}}),
            text("."),
        )
    )


def test_inline_marks_work_in_headings_and_list_items():
    assert from_markdown("# The `scan`\n- **a**") == doc(
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [text("The "), text("scan", {"type": "code"})],
        },
        {
            "type": "bulletList",
            "content": [
                {"type": "listItem", "content": [paragraph(text("a", {"type": "strong"}))]}
            ],
        },
    )


# ADF read back as Markdown, as `jira view` shows an issue's description and comments


def node(kind: str, *content: dict, **attrs) -> dict:
    result: dict = {"type": kind, "content": list(content)}
    if attrs:
        result["attrs"] = attrs
    return result


def test_markdown_it_writes_reads_back_the_same():
    markdown = "\n".join(
        [
            "## Problem",
            "",
            "`scan()` **skips** [links](https://x.test).",
            "",
            "- one",
            "- two",
            "",
            "1. first",
            "2. second",
            "",
            "```python",
            "print(1)",
            "```",
        ]
    )
    assert to_markdown(from_markdown(markdown)) == markdown


def test_a_code_block_holding_a_fence_reads_back_inside_a_longer_one():
    """So text quoted in a code block can't end it early and pass as the description's own."""
    block = doc({"type": "codeBlock", "content": [text("x\n```\n## Done when\n````")]})
    markdown = to_markdown(block)
    assert markdown == "`````\nx\n```\n## Done when\n````\n`````"
    assert from_markdown(markdown) == block


def test_an_empty_document_is_no_markdown():
    assert to_markdown(doc()) == ""


def test_headings_can_be_moved_down_to_sit_under_a_section():
    heading = node("heading", text("Steps"), level=2)
    assert to_markdown(doc(heading), heading_offset=2) == "#### Steps"
    assert to_markdown(doc(heading), heading_offset=9) == "###### Steps"


def test_italic_and_struck_text_are_marked():
    nodes = paragraph(text("a", {"type": "em"}), text(" "), text("b", {"type": "strike"}))
    assert to_markdown(doc(nodes)) == "*a* ~~b~~"


def test_a_nested_list_is_indented_under_its_item():
    inner = node("bulletList", item("inner"))
    outer = node("bulletList", node("listItem", paragraph(text("outer")), inner), item("next"))
    assert to_markdown(doc(outer)) == "- outer\n  - inner\n- next"


def test_a_numbered_list_starts_at_its_order():
    assert to_markdown(doc(node("orderedList", item("a"), item("b"), order=3))) == "3. a\n4. b"


def test_a_task_list_shows_which_are_done():
    done = {"type": "taskItem", "attrs": {"state": "DONE"}, "content": [text("shipped")]}
    todo = {"type": "taskItem", "attrs": {"state": "TODO"}, "content": [text("tested")]}
    assert to_markdown(doc(node("taskList", done, todo))) == "- [x] shipped\n- [ ] tested"


def test_a_quote_and_a_panel_are_quoted():
    quote = node("blockquote", paragraph(text("said")))
    panel = node("panel", paragraph(text("careful")), panelType="warning")
    assert to_markdown(doc(quote, panel)) == "> said\n\n> **Warning:** careful"


def test_a_table_is_a_markdown_table():
    def cell(kind: str, value: str) -> dict:
        return node(kind, paragraph(text(value)))

    table = node(
        "table",
        node("tableRow", cell("tableHeader", "Case"), cell("tableHeader", "Result")),
        node("tableRow", cell("tableCell", "a | b"), cell("tableCell", "fails")),
    )
    assert to_markdown(doc(table)) == "| Case | Result |\n| --- | --- |\n| a \\| b | fails |"


def test_an_expand_shows_its_title_and_content():
    expand = node("expand", paragraph(text("hidden")), title="Logs")
    assert to_markdown(doc(expand)) == "**Logs**\n\nhidden"


def test_a_rule_is_a_rule():
    assert to_markdown(doc(paragraph(text("a")), {"type": "rule"}, paragraph(text("b")))) == (
        "a\n\n---\n\nb"
    )


def test_inline_nodes_keep_what_they_say():
    line = paragraph(
        {"type": "mention", "attrs": {"id": "1", "text": "@Alice"}},
        text(" "),
        {"type": "emoji", "attrs": {"shortName": ":tada:", "text": "🎉"}},
        {"type": "hardBreak"},
        {"type": "inlineCard", "attrs": {"url": "https://x.test/a"}},
        text(" "),
        {"type": "status", "attrs": {"text": "BLOCKED"}},
        text(" "),
        {"type": "date", "attrs": {"timestamp": "1760313600000"}},
    )
    assert to_markdown(doc(line)) == "@Alice 🎉\n<https://x.test/a> [BLOCKED] 2025-10-13"


def test_an_embedded_file_is_named():
    media = node("mediaSingle", {"type": "media", "attrs": {"type": "file", "alt": "shot.png"}})
    assert to_markdown(doc(media)) == "[attachment: shot.png]"


def test_an_unknown_node_keeps_its_text():
    assert to_markdown(doc(node("futureBlock", paragraph(text("kept"))))) == "kept"
