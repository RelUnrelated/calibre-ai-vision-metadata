"""Deterministic parsing helpers for comic/archive filenames.

The parser deliberately keeps the original string untouched.  It produces
candidates and evidence; an ambiguous candidate is never treated as fact.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


EVENT_RE = re.compile(r"(?<![A-Za-z0-9])[Cc]\d{2,4}(?![A-Za-z0-9])")
BRACKET_RE = re.compile(r"\[([^\]]*)\]")
PAREN_RE = re.compile(r"\(([^()]*)\)")
HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")
LATIN_RE = re.compile(r"[A-Za-z]")
HAN_RE = re.compile(r"[\u3400-\u9fff]")
NUMERIC_SUFFIX_RE = re.compile(r"\s*[（(](\d+)[）)]\s*$")

# Python adaptation of Kavita's explicit manga volume/chapter conventions.
# See THIRD_PARTY_NOTICES.md. Local event/creator/title rules take precedence.
NUMBER = r"[0-9]+(?:\.[0-9]+)?"
VOLUME_LABEL = r"(?:volume|vol|tome|v|t)\.?[\s_]*"
CHAPTER_LABEL = r"(?:chapters?|chp|ch|c)\.?[\s_]*"
VOLUME_RE = re.compile(
    rf"(?<![A-Za-z0-9]){VOLUME_LABEL}(?P<latin>{NUMBER}(?:\s*-\s*(?:{VOLUME_LABEL})?{NUMBER})?)(?![A-Za-z0-9.])"
    rf"|(?:第\s*)?(?P<suffix>{NUMBER}(?:\s*-\s*{NUMBER})?)\s*[巻卷册冊]"
    rf"|[巻卷册冊]\s*(?P<prefix>{NUMBER}(?:\s*-\s*{NUMBER})?)", re.IGNORECASE)
CHAPTER_RE = re.compile(
    rf"(?<![A-Za-z0-9]){CHAPTER_LABEL}(?P<latin>{NUMBER}(?:\s*-\s*(?:{CHAPTER_LABEL})?{NUMBER})?)(?![A-Za-z0-9.])"
    rf"|(?:第\s*)?(?P<suffix>{NUMBER}(?:\s*-\s*{NUMBER})?)\s*[話话]", re.IGNORECASE)


@dataclass
class TitleNumbering:
    base: str
    volume: str = ''
    chapter: str = ''
    volume_range: str = ''
    chapter_range: str = ''
    evidence: list[str] = field(default_factory=list)


def parse_title_numbering(title: str) -> TitleNumbering:
    """Parse explicit markers first; bare terminal numbers remain volumes.

    Call on title text only, after protecting creator/publication/event groups.
    Ranges stay separate because calibre's series index is a single number.
    """
    safe = EVENT_RE.sub(' ', title)
    matches = sorted([(m, 'volume') for m in VOLUME_RE.finditer(safe)] +
                     [(m, 'chapter') for m in CHAPTER_RE.finditer(safe)],
                     key=lambda item: item[0].start())
    result = TitleNumbering(base=title)
    seen = set()
    for match, kind in matches:
        value = next(v for v in match.groups() if v is not None)
        # Remove repeated labels in true ranges, e.g. v1-v2 / ch1-ch4.
        numbers = re.findall(NUMBER, value)
        value = '-'.join(str(int(n.split('.')[0])) + ('.' + n.split('.')[1] if '.' in n else '')
                         for n in numbers)
        if kind in seen:
            result.evidence.append('ignored-duplicate-' + kind + ': ' + match.group(0))
            continue
        seen.add(kind)
        setattr(result, kind + ('_range' if len(numbers) > 1 else ''), value)
        result.evidence.append('explicit-' + kind + '-marker: ' + value)
    if matches:
        # Everything after the first marker is issue/subtitle/extra information,
        # rather than the series name. The original title remains available.
        result.base = safe[:matches[0][0].start()].strip(' \t_-')
        if 'volume' not in seen:
            terminal = re.match(rf'^(.+?)({NUMBER})$', result.base)
            if terminal:
                result.base, result.volume = terminal.group(1).rstrip(' _-'), terminal.group(2)
                result.evidence.append('terminal-title-volume-number: ' + result.volume)
    else:
        terminal = re.match(rf'^(.+?)(?P<number>{NUMBER})$', safe)
        if terminal:
            result.base = terminal.group(1).rstrip(' _-')
            result.volume = terminal.group('number')
            result.evidence.append('terminal-title-volume-number: ' + result.volume)
    if not result.base:
        result.volume = result.chapter = result.volume_range = result.chapter_range = ''
    return result


def _is_numbering_group(value: str) -> bool:
    return bool(VOLUME_RE.fullmatch(value) or CHAPTER_RE.fullmatch(value)) and not EVENT_RE.fullmatch(value)


@dataclass
class FilenameParseResult:
    original_filename: str
    original_title: str = ""
    translated_title: str = ""
    series: str = ""
    volume: str = ""
    chapter: str = ""
    volume_range: str = ""
    chapter_range: str = ""
    title_source: str = "unknown"
    title_language_hint: str = "unknown"
    title_candidate_kind: str = "none"
    author_candidate_kind: str = "none"
    creators: list[str] = field(default_factory=list)
    circle: str = ""
    translation_group: str = ""
    source_publication: str = ""
    event_code: str = ""
    edition: str = ""
    filename_suffix: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    review_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_translation_group(value: str) -> bool:
    text = value.strip().lower()
    return any(token in text for token in ("汉化", "翻译", "翻譯", "译", "譯", "扫图", "掃圖"))


def _looks_like_chinese_title(value: str) -> bool:
    value = value.strip()
    if not value or not HAN_RE.search(value):
        return False
    # A leading Japanese kana marker makes this a Japanese title candidate.
    # Han characters can be mixed with Korean Hangul or Latin words; those
    # titles must go through translation instead of being accepted as Chinese.
    # Remove explicit numbering first so ``中文标题 Vol. 2`` remains Chinese.
    language_probe = VOLUME_RE.sub(' ', value)
    language_probe = CHAPTER_RE.sub(' ', language_probe)
    return not HIRAGANA_KATAKANA_RE.search(value) and not HANGUL_RE.search(value) and not LATIN_RE.search(language_probe)


def _clean_title(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t-_[]()\\")
    return value.strip()


def read_filename_source(db: Any, book_id: int) -> dict[str, str]:
    """Read the user column first; identify a calibre directory fallback."""
    original = db.field_for('#original_filename', book_id, '') if '#original_filename' in db.field_metadata else ''
    if original and str(original).strip():
        return {'original_filename': str(original), 'original_filename_source': 'custom_column',
                'calibre_directory_name': ''}
    directory = str(db.field_for('path', book_id, '') or '').replace('\\', '/').rsplit('/', 1)[-1]
    candidate = re.sub(r'\s*\(' + str(book_id) + r'\)$', '', directory)
    return {'original_filename': candidate, 'original_filename_source': 'calibre_path_fallback',
            'calibre_directory_name': directory}


def select_title_evidence(parsed: FilenameParseResult, existing_title: str,
                          filename_source: str = 'custom_column') -> tuple[FilenameParseResult, str]:
    """A current title can retain text that calibre truncated in its directory."""
    current = parse_filename(existing_title or '')
    current_has_title = bool(current.translated_title or current.original_title)
    if (existing_title or '').strip().casefold() in {'unknown', '未知', '未知书名'}:
        current_has_title = False
        current = parse_filename('')
    if filename_source not in {'custom_column', 'analysis_history'} and existing_title:
        # calibre may transliterate directories to Latin text and truncate them.
        # Prefer the actual title even when it proves that no title is available.
        return current, 'existing_title'
    if current_has_title and not (parsed.translated_title or parsed.original_title):
        return current, 'existing_title'
    return parsed, 'filename'


def parse_filename(original_filename: str) -> FilenameParseResult:
    """Parse common manga naming structures without rewriting the input."""
    raw = original_filename or ""
    result = FilenameParseResult(original_filename=raw)
    stem = re.sub(r"\.(?:cbz|cbr|zip|rar|pdf|epub|mobi|azw3?)$", "", raw, flags=re.IGNORECASE).strip()
    suffix = NUMERIC_SUFFIX_RE.search(stem)
    if suffix:
        # Download/import collision suffixes are not evidence of a volume.
        result.filename_suffix = suffix.group(0).strip()
        result.evidence.append("ambiguous-numeric-filename-suffix: " + result.filename_suffix)
        stem = stem[:suffix.start()].rstrip()

    bracket_values = [m.group(1).strip() for m in BRACKET_RE.finditer(stem) if m.group(1).strip()]
    paren_values = [m.group(1).strip() for m in PAREN_RE.finditer(stem) if m.group(1).strip()]

    for value in bracket_values:
        if _is_translation_group(value) and not result.translation_group:
            result.translation_group = value
            result.evidence.append("translation-group: " + value)
        elif value.lower() in {"dl版", "dl", "digital", "数字版"} and not result.edition:
            result.edition = value
            result.evidence.append("edition: " + value)

    event = EVENT_RE.search(stem)
    if event:
        result.event_code = event.group(0).upper()
        result.evidence.append("event-code: " + result.event_code)

    # [Circle(Author)] is the strongest author evidence in the supported forms.
    for value in bracket_values:
        if _is_translation_group(value):
            continue
        match = re.match(r"^(.+?)\(([^()]+)\)$", value)
        if match:
            circle, author = match.group(1).strip(), match.group(2).strip()
            if circle and author and not result.circle:
                result.circle = circle
                result.creators = [author]
                result.author_candidate_kind = 'circle_author'
                result.evidence.extend(["circle: " + circle, "author-in-circle: " + author])

    if not result.creators:
        for value in bracket_values:
            lower = value.lower()
            if (_is_translation_group(value) or value.lower() in {"dl版", "dl", "digital", "数字版"}
                    or EVENT_RE.fullmatch(value) or _is_numbering_group(value) or "comic" in lower or "vol." in lower):
                continue
            if value and not any(ch in value for ch in "[]"):
                result.creators = [value]
                result.author_candidate_kind = 'bracket_guess'
                result.evidence.append("standalone-author-candidate: " + value)
                break

    # Unbracketed text is stronger title evidence than metadata brackets. For
    # [Author]Title[translation][notes], the trailing brackets are annotations,
    # even if one happens to contain Chinese characters.
    candidate = BRACKET_RE.sub(' ', stem)
    candidate = re.sub(r"\\(?=\()", "", candidate)
    candidate = PAREN_RE.sub(' ', candidate)
    candidate = EVENT_RE.sub(' ', candidate)
    candidate = re.sub(r"\\(?=\s*[([])", ' ', candidate)
    candidate = _clean_title(candidate)

    # A leading, non-bracket segment containing Chinese characters is an explicit
    # translated title.  Do this before removing metadata groups.
    # Square brackets delimit common author/translation groups. Parentheses can
    # be part of the work title, e.g. ``种马(救世主)``; do not cut a title there.
    leading = stem.split('[', 1)[0].strip()
    if leading.startswith('(') and ')' in leading:
        leading = leading[leading.find(')') + 1:].strip()
    chinese_title = leading if _looks_like_chinese_title(leading) and not _is_translation_group(leading) else ""
    bracket_titles = [v for v in bracket_values if v not in result.creators
                      and not _is_translation_group(v) and not EVENT_RE.fullmatch(v) and not _is_numbering_group(v)
                      and not re.search(r"[()]", v)
                      and v.lower() not in {"dl版", "dl", "digital", "数字版"}
                      and not re.search(r"comic|vol\.", v, re.IGNORECASE)]
    # Common form: [Author][Title][Circle (Author)]. Only a unique remaining
    # bracket is accepted only when there is no unbracketed title text.
    bracket_title = bracket_titles[0] if not candidate and len(bracket_titles) == 1 and result.creators else ""
    result.title_candidate_kind = 'unbracketed' if candidate else ('bracketed' if bracket_title else 'none')
    if not chinese_title and _looks_like_chinese_title(bracket_title):
        chinese_title = bracket_title
    if chinese_title:
        result.translated_title = _clean_title(chinese_title)
        result.title_source = "filename"
        result.evidence.append("han-title-language-ambiguous: " + result.translated_title)

    if result.translated_title and candidate.startswith(result.translated_title):
        remainder = _clean_title(candidate[len(result.translated_title):])
        if remainder and re.search(r'[()（）]', result.translated_title):
            # A Chinese prefix followed by an unbracketed Japanese/Korean title
            # is one mixed work title, not a complete translated title.
            candidate = _clean_title(result.translated_title + ' ' + remainder)
            result.original_title = candidate
            result.translated_title = ''
            result.title_source = 'unknown'
        else:
            candidate = remainder
    if candidate:
        result.original_title = candidate
        result.evidence.append("title-candidate: " + candidate)
    elif bracket_title and not result.translated_title:
        result.original_title = _clean_title(bracket_title)
        result.evidence.append("bracket-title-candidate: " + result.original_title)

    # Chinese titles also commonly follow leading author/circle groups.
    if not result.translated_title and _looks_like_chinese_title(candidate) and not _is_translation_group(candidate):
        result.translated_title = candidate
        result.original_title = ''
        result.title_source = 'filename'
        result.evidence.append('han-title-language-ambiguous: ' + candidate)
    if result.translated_title:
        # Han characters alone are shared by Chinese and Japanese. Retain the
        # source wording provisionally, but allow validated language analysis.
        result.title_language_hint = ('zh' if HIRAGANA_KATAKANA_RE.search(result.original_title)
                                      else 'han_ambiguous')
    elif HIRAGANA_KATAKANA_RE.search(result.original_title):
        result.title_language_hint = 'ja'
    elif HANGUL_RE.search(result.original_title):
        result.title_language_hint = 'ko'
    elif LATIN_RE.search(result.original_title) and not HAN_RE.search(result.original_title):
        result.title_language_hint = 'en'
    title_for_volume = result.translated_title or result.original_title
    # Only standalone numbering groups are eligible; publication names such as
    # (COMIC magazine Vol.18) must never supply this work's volume.
    numbering_groups = [v for v in bracket_values + paren_values if _is_numbering_group(v)]
    numbering_input = title_for_volume + (' ' + ' '.join(numbering_groups) if numbering_groups else '')
    numbering = parse_title_numbering(numbering_input)
    result.volume, result.chapter = numbering.volume, numbering.chapter
    result.volume_range, result.chapter_range = numbering.volume_range, numbering.chapter_range
    if any((result.volume, result.chapter, result.volume_range, result.chapter_range)):
        result.series = _clean_title(numbering.base)
    result.evidence.extend(numbering.evidence)

    # Parenthesized publication names are evidence, not part of an independent
    # work title.  Keep the value for review rather than guessing which one wins.
    publication_tokens = [v for v in paren_values if v and not EVENT_RE.fullmatch(v)
                          and v not in result.creators and v != result.circle and not _is_numbering_group(v)]
    if publication_tokens:
        result.source_publication = publication_tokens[-1]
        result.evidence.append("publication-candidate: " + result.source_publication)

    if result.translated_title:
        result.confidence = 0.92
    elif result.original_title and result.creators:
        result.confidence = 0.82
    elif result.original_title:
        result.confidence = 0.62
    result.review_required = result.confidence < 0.85 or not result.original_title or bool(result.filename_suffix)
    return result
