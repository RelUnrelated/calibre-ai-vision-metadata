"""Provider-independent normalization and validation for AI results."""

from __future__ import annotations

import json
import re
from typing import Any

try:
    from calibre_plugins.ai_vision_metadata.filename_parser import FilenameParseResult, parse_filename, select_title_evidence, parse_title_numbering, HIRAGANA_KATAKANA_RE, HANGUL_RE, VOLUME_RE, CHAPTER_RE, NUMBER
    from calibre_plugins.ai_vision_metadata.filename_roles import resolve_filename_roles
except ImportError:  # Allows the pure parser/schema tests to run outside calibre.
    from filename_parser import FilenameParseResult, parse_filename, select_title_evidence, parse_title_numbering, HIRAGANA_KATAKANA_RE, HANGUL_RE, VOLUME_RE, CHAPTER_RE, NUMBER
    from filename_roles import resolve_filename_roles


KNOWN_KEYS = {
    "series", "volume", "issue_number", "title", "creators", "author", "publisher",
    "ids", "identifiers", "format_type", "comments", "tags", "languages", "pub_year",
    "pub_month", "pub_day", "original_title", "translated_title", "translation_status",
    "confidence", "evidence", "review_required", "circle", "translation_group",
    "source_publication", "event_code", "edition",
    "filename_roles",
}

METADATA_CONTENT_KEYS = KNOWN_KEYS - {
    'confidence', 'evidence', 'review_required', 'publisher', 'ids', 'identifiers',
    'pub_year', 'pub_month', 'pub_day', 'tags', 'format_type', 'translation_status',
}


def _skip_json_fragment(text: str, start: int) -> int:
    """Skip a malformed container as a whole, never recover its nested objects."""
    stack = []
    quoted = escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in '{[':
            stack.append(char)
        elif char in '}]':
            if not stack:
                return index + 1
            stack.pop()
            if not stack:
                return index + 1
    return len(text)


def extract_metadata_json(text: str) -> dict[str, Any]:
    """Decode complete top-level objects and ignore format/schema preambles.

    Multiple different metadata objects are ambiguous and rejected. Arrays,
    schema properties, and nested objects in malformed JSON are not promoted
    into a metadata result. No attempt is made to repair truncated JSON.
    """
    if not isinstance(text, str):
        raise ValueError('AI response content must be text')
    decoder = json.JSONDecoder()
    candidates = []
    position = 0
    while position < len(text):
        char = text[position]
        if char not in '{["':
            position += 1
            continue
        try:
            value, end = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            position = _skip_json_fragment(text, position) if char in '{[' else position + 1
            continue
        position = end
        if isinstance(value, dict) and METADATA_CONTENT_KEYS.intersection(value):
            if value not in candidates:
                candidates.append(value)
    if not candidates:
        raise ValueError('No complete metadata JSON object was found in the AI response')
    if len(candidates) != 1:
        raise ValueError('The AI returned multiple different metadata objects; retry the analysis')
    return candidates[0]


def tag_allowlist_for_library(db: Any, configured_tags: Any = ()) -> list[str]:
    """Return this library's existing tags plus explicitly authorized tags."""
    values = {str(x).strip() for x in (configured_tags or []) if str(x).strip()}
    try:
        values.update(str(x).strip() for x in db.all_field_names("tags") if str(x).strip())
    except (AttributeError, KeyError, TypeError):
        pass
    return sorted(values, key=str.casefold)


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _list_of_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [x.strip() for x in value.split(",") if x.strip()]
    if isinstance(value, (list, tuple)):
        return [_string(x) for x in value if _string(x)]
    return []


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _format_volume_title(title: str, volume: str, chapter: str = '') -> tuple[str, str]:
    """Use one base for title and series, only after source volume evidence."""
    base = parse_title_numbering(title).base
    base = re.sub(r'\s+', ' ', base).strip()
    suffix = f' 第{chapter}话' if chapter else ''
    return (f'{base} {volume}{suffix}', base) if base else ('', '')


def _remove_unsupported_numbering(title: str, source: FilenameParseResult) -> str:
    """Do not let an AI promote publication/annotation numbers into a title.

    Work numbering is restored separately from the validated source. Internal
    title digits remain intact. A bare suffix with literal source-title evidence
    is kept; Chinese/Japanese written numerals may legitimately become digits.
    """
    if any((source.volume, source.volume_range, source.chapter, source.chapter_range)):
        return title
    source_title = source.translated_title or source.original_title
    clean_source = parse_filename(source_title)
    source_title = clean_source.translated_title or clean_source.original_title
    # Explicit volume/chapter markers are unsupported even when an unrelated
    # digit exists inside the source title.
    cleaned = VOLUME_RE.sub(' ', title)
    cleaned = CHAPTER_RE.sub(' ', cleaned)
    suffix = re.search(rf'(?P<number>{NUMBER}(?:\s*-\s*{NUMBER})?)\s*$', cleaned)
    if suffix:
        numbers = re.findall(NUMBER, suffix.group('number'))
        source_numbers = re.findall(NUMBER, source_title)
        written_numerals = re.search(r'[零〇一二三四五六七八九十百千万萬两兩壱弐参]', source_title)
        if not written_numerals and any(number not in source_numbers for number in numbers):
            cleaned = cleaned[:suffix.start()]
    return re.sub(r'\s+', ' ', cleaned).strip(' \t_-')


def normalize_result(raw: Any, original_filename: str, parsed: FilenameParseResult | None = None,
                     allowed_tags: set[str] | None = None, *, existing_title: str = "",
                     filename_source: str = "custom_column", comments_context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a conservative, UI-compatible result.

    Unknown keys are ignored, list and scalar types are normalized, and filename
    evidence always wins over an AI-generated title.
    """
    if not isinstance(raw, dict):
        raise ValueError("AI response must be a JSON object")
    parsed = parsed or parse_filename(original_filename)
    title_parsed, title_input_source = select_title_evidence(parsed, existing_title, filename_source)
    metadata_parsed = title_parsed if filename_source not in {'custom_column', 'analysis_history'} and existing_title else parsed
    data = {str(k): v for k, v in raw.items() if str(k) in KNOWN_KEYS}
    role_status, filename_roles, role_warnings = 'legacy', {}, []
    if 'filename_roles' in data:
        title_parsed, role_status, filename_roles, role_warnings = resolve_filename_roles(title_parsed, data['filename_roles'])
    if role_status in {'accepted', 'title_only'}:
        metadata_parsed = title_parsed

    creators = _list_of_strings(data.get("creators"))
    if not creators:
        creators = _list_of_strings(data.get("author"))
    if metadata_parsed.creators or title_parsed.creators:
        creators = metadata_parsed.creators or title_parsed.creators
    if role_status in {'accepted', 'title_only'}:
        creators = title_parsed.creators

    original_title = title_parsed.original_title or _string(data.get("original_title"))
    # Models sometimes echo whole filenames. Strip their metadata groups before
    # displaying a proposed title, while deterministic Chinese evidence wins.
    ai_translation = parse_filename(_string(data.get('translated_title')))
    ai_title = parse_filename(_string(data.get('title')))
    annotations = {value.strip() for value in re.findall(r'\[([^\]]*)\]', title_parsed.original_filename)}
    annotations.difference_update({title_parsed.translated_title, title_parsed.original_title})
    discarded_annotation = False
    discarded_japanese_translation = False
    discarded_korean_translation = False
    removed_ai_numbering = []
    for candidate in (ai_translation, ai_title):
        if (candidate.translated_title or candidate.original_title) in annotations:
            candidate.translated_title = candidate.original_title = ''
            discarded_annotation = True
        if HIRAGANA_KATAKANA_RE.search(candidate.translated_title or candidate.original_title):
            # translated_title can echo the source while title holds a valid
            # Chinese translation. Reject kana-bearing candidates before
            # choosing precedence, rather than overwriting the valid field.
            candidate.translated_title = candidate.original_title = ''
            discarded_japanese_translation = True
        if HANGUL_RE.search(candidate.translated_title or candidate.original_title):
            candidate.translated_title = candidate.original_title = ''
            discarded_korean_translation = True
        for field in ('translated_title', 'original_title'):
            text = getattr(candidate, field)
            if text:
                cleaned = _remove_unsupported_numbering(text, title_parsed)
                if cleaned != text:
                    removed_ai_numbering.append(text)
                    setattr(candidate, field, cleaned)
    translated_title = title_parsed.translated_title or ai_translation.translated_title or ai_translation.original_title or ai_title.translated_title
    title = title_parsed.translated_title or translated_title or ai_title.translated_title or ai_title.original_title or original_title
    title_source = title_input_source if title_parsed.translated_title else ("ai_translated" if translated_title else "unknown")
    warnings = list(role_warnings)
    if removed_ai_numbering:
        warnings.append('Removed AI numbering without work-title evidence: ' + '; '.join(dict.fromkeys(removed_ai_numbering)))
    source_language = title_parsed.title_language_hint
    source_is_translatable = source_language in {'ja', 'ko', 'en'}
    translation_status = 'not_required'
    if source_is_translatable and not title_parsed.translated_title:
        translation_status = ('translated' if title and (title != original_title or (
                                  not HIRAGANA_KATAKANA_RE.search(original_title)
                                  and _string(data.get('translated_title')) == title))
                              and not HIRAGANA_KATAKANA_RE.search(title) else 'needs_translation')
        if translation_status == 'translated':
            translated_title = title
            title_source = 'ai_translated'
        if translation_status == 'needs_translation':
            language_name = {'ja': '日文', 'ko': '韩文', 'en': '英文'}.get(source_language, '外文')
            warnings.append(f'{language_name}原文未翻译为中文，已跳过自动写入。')
    if discarded_japanese_translation:
        warnings.append('An AI translation still contained Japanese kana and was rejected.')
    if discarded_korean_translation:
        warnings.append('An AI translation still contained Korean Hangul and was rejected.')
    if discarded_annotation:
        warnings.append('An AI title repeated a filename annotation and was rejected. The source title is preserved if no valid translation remains.')
    title_needs_confirmation = False
    # A calibre directory ends in its book ID, e.g. "Title (2)". It must
    # never be promoted to a recovered source filename or used as a volume.
    if filename_source == 'analysis_history':
        warnings.append('Title evidence was recovered from plugin history because #original_filename is unavailable; verify the historical input if needed.')
    elif filename_source != "custom_column":
        warnings.append("#original_filename is empty or unavailable. The displayed source is a calibre directory, not the original filename.")
    if filename_source == 'custom_column':
        comments = original_filename
        comments_source = 'custom_column'
        comments_write_allowed = bool(comments)
    else:
        captured = comments_context if comments_context is not None else {
            'text': existing_title, 'source': 'existing_title_snapshot', 'write_allowed': bool(existing_title),
        }
        comments = captured.get('text') or ''
        comments_source = captured.get('source', 'unavailable')
        comments_write_allowed = bool(comments and captured.get('write_allowed'))
        if comments_source == 'analysis_history' and comments:
            warnings.append('Comments preserves input text recovered from plugin history; the original filename column is unavailable.')
        elif comments_source == 'existing_title_snapshot' and comments:
            warnings.append('Comments preserves the complete title text captured before this analysis. The original filename cannot be verified without #original_filename.')
    if title_input_source == 'existing_title':
        warnings.append("Title evidence was recovered from the current title. Confirm the cleaned title and any AI translation before writing.")
        title_needs_confirmation = True
        if not title_parsed.translated_title:
            title_source = 'ai_translated' if translated_title or ai_title.translated_title else 'existing_title'
    if not (title_parsed.translated_title or title_parsed.original_title):
        warnings.append("The filename contains no supported title. Confirm the current title manually; no title can be inferred from the cover.")
        title = ''
        original_title = translated_title = ""
        title_source = "existing_title" if title else "unknown"
        title_needs_confirmation = True
        data["series"] = data["volume"] = data["issue_number"] = ""
    if title_parsed.filename_suffix:
        warnings.append("A trailing parenthesized number is ambiguous and is not used as a volume.")
        if not title_parsed.translated_title:
            title = re.sub(r'\s*' + re.escape(title_parsed.filename_suffix) + r'$', '', title).rstrip()
            translated_title = re.sub(r'\s*' + re.escape(title_parsed.filename_suffix) + r'$', '', translated_title).rstrip()
        if not title_parsed.volume:
            data["volume"] = data["issue_number"] = ""
    languages = ["zho"] if metadata_parsed.translation_group else _list_of_strings(data.get("languages"))
    effective_parsed = title_parsed if role_status in {'accepted', 'title_only'} else parsed
    confidence = data.get("confidence", effective_parsed.confidence if original_filename else 1.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = effective_parsed.confidence

    review_required = bool(data.get("review_required", False))
    review_required = review_required or (bool(original_filename) and effective_parsed.review_required) or confidence < 0.85
    if not original_title or not title:
        review_required = True
    review_required = review_required or bool(warnings)
    # A model repeating a standalone title in "series" is not series evidence.
    # Only retain series/index suggestions when the title text supplies a volume.
    volume = title_parsed.volume
    series = ''
    if title_parsed.volume_range:
        warnings.append('A volume range is preserved as evidence; no single calibre series index is suggested.')
        review_required = True
        base = parse_title_numbering(title).base
        title = f'{base} {title_parsed.volume_range}' if base else title
    chapter = title_parsed.chapter or title_parsed.chapter_range
    if not volume and chapter and title:
        base = parse_title_numbering(title).base
        title = f'{base} 第{chapter}话' if base else title
    if volume and title:
        title, series = _format_volume_title(title, volume, title_parsed.chapter or title_parsed.chapter_range)
        if translated_title:
            translated_title = title
        if not series:
            volume = ''
    if translated_title and title:
        translated_title = title

    result = {
        "original_filename": original_filename,
        "original_title": original_title,
        "translated_title": translated_title,
        "title_source": title_source,
        "title_language_hint": title_parsed.title_language_hint,
        "translation_status": translation_status,
        "provider_title": _string(data.get('title')),
        "provider_translated_title": _string(data.get('translated_title')),
        "title_needs_confirmation": title_needs_confirmation,
        "original_filename_source": filename_source,
        "warnings": warnings,
        "cover_image_supplied": False,
        "title": title,
        "creators": creators,
        "circle": metadata_parsed.circle or title_parsed.circle or _string(data.get("circle")),
        "translation_group": metadata_parsed.translation_group or title_parsed.translation_group or _string(data.get("translation_group")),
        "source_publication": metadata_parsed.source_publication or title_parsed.source_publication or _string(data.get("source_publication")),
        "event_code": metadata_parsed.event_code or title_parsed.event_code or _string(data.get("event_code")),
        "edition": metadata_parsed.edition or title_parsed.edition or _string(data.get("edition")),
        "series": series,
        "volume": volume,
        "issue_number": "",
        "chapter": title_parsed.chapter,
        "volume_range": title_parsed.volume_range,
        "chapter_range": title_parsed.chapter_range,
        "publisher": "",
        "ids": "",
        "format_type": _string(data.get("format_type")),
        "comments": comments,
        "comments_source": comments_source,
        "comments_write_allowed": comments_write_allowed,
        "tags": [],
        "languages": languages,
        "pub_year": None,
        "pub_month": None,
        "pub_day": None,
        "confidence": confidence,
        "evidence": parsed.evidence + (["existing-title: " + item for item in title_parsed.evidence]
                                     if title_input_source == 'existing_title' else [])
                    + ([item for item in title_parsed.evidence if item.startswith('ai-role-')]
                       if role_status in {'accepted', 'title_only'} and title_input_source != 'existing_title' else [])
                    + _list_of_strings(data.get("evidence")),
        "review_required": review_required,
        "title_only": role_status == 'title_only',
        "filename_role_status": role_status,
        "filename_roles": filename_roles,
    }
    return result
