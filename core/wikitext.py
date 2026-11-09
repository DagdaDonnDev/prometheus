"""
Wikipedia markup → plain text. Shared by the Simple English extractor
(ingest.py) and the full English builder (core/wiki_full.py).

Templates are removed innermost-first with a regex loop (C speed) instead of
walking the text a character at a time — that matters for a million articles.
"""

import re

# Sections that are lists of links and sources, not article text
_TAIL = re.compile(
    r"^==+\s*(References|External links|See also|Further reading|Notes|Footnotes|"
    r"Bibliography|Sources|Citations|Notes and references|Works cited)\s*==+\s*$",
    re.I | re.M)
_INNER_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_INNER_TABLE = re.compile(r"\{\|[^{}]*?\|\}", re.S)


def clean_wikitext(text: str, cut_tail: bool = False, max_words: int = 0) -> str:
    """
    Step 1: references and comments (before tags go, or citation text leaks in)
    Step 2: templates {{…}} and tables {|…|}, innermost first, nested any depth
    Step 3: files, images, categories; links → their text; external links
    Step 4: leftover HTML tags and table lines
    Step 5: headings and bold/italic markup (keep the words)
    Step 6: whitespace; optionally cut the reference sections and long tails
    """
    if cut_tail:
        m = _TAIL.search(text)
        if m:
            text = text[:m.start()]

    # Step 1
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)

    # Step 2
    for _ in range(12):
        new = _INNER_TEMPLATE.sub("", text)
        if new == text:
            break
        text = new
    text = text.replace("{{", "").replace("}}", "")
    for _ in range(6):
        new = _INNER_TABLE.sub("", text)
        if new == text:
            break
        text = new

    # Step 3
    text = re.sub(r"\[\[(?:File|Image|Category):[^\]]*\]\]", "", text, flags=re.I)
    text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", "", text)

    # Step 4
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"^\s*[|!].*$", "", text, flags=re.M)
    text = re.sub(r"^\s*\{\|.*$", "", text, flags=re.M)
    text = re.sub(r"^\s*\|\}.*$", "", text, flags=re.M)

    # Step 5
    text = re.sub(r"={2,}([^=]+)={2,}", r"\1", text)
    text = re.sub(r"'{2,}", "", text)

    # Step 6
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    if max_words:
        words = text.split(" ")
        if len(words) > max_words:
            text = " ".join(words[:max_words]) + " …"
    return text


def title_key(title: str) -> str:
    """
    The lookup key for a title — the same as the extracted file names, lower
    case ("Inception (film)" → "inception_film", "BT-7274" → "bt-7274").
    """
    t = title.replace("_", " ")
    t = re.sub(r"[^\w\s-]", "", t)
    return re.sub(r"\s+", "_", t.strip())[:100].lower()
