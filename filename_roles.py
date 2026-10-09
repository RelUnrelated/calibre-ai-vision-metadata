"""Validate AI role assignments against literal filename evidence."""

from __future__ import annotations

from dataclasses import replace
import math
import re
from typing import Any

try:
    from calibre_plugins.ai_vision_metadata.filename_parser import FilenameParseResult, parse_filename, HIRAGANA_KATAKANA_RE, HANGUL_RE, HAN_RE
except ImportError:
    from filename_parser import FilenameParseResult, parse_filename, HIRAGANA_KATAKANA_RE, HANGUL_RE, HAN_RE


def _is_annotation(text: str) -> bool:
    return bool(re.search(
        r'^(?:.*(?:汉化组|漢化組|翻译组|翻譯組|扫图组|掃圖組)|'
        r'(?:中国|中國|中文|简体|簡體|繁体|繁體)?(?:翻译|翻譯)|'
        r'(?:禁漫)?(?:去码|去碼|无码|無碼|无修正|無修正)|全彩|'
        r'修订版|修訂版|校对|校對|扫图|掃圖|DL版|数字版|數字版|'
        r'C\d{2,4}|DL|digital|uncensored|カラー|フルカラー)$', text, re.IGNORECASE))


def resolve_filename_roles(parsed: FilenameParseResult, roles: Any
                           ) -> tuple[FilenameParseResult, str, dict[str, Any], list[str]]:
    """Resolve roles only from verbatim quotes; preserve clear Chinese wording.

    A first-bracket author guess can be corrected. Explicit Circle(Author)
    evidence and an unambiguous Chinese title cannot be replaced by a guess.
    The caller skips automatic writes for invalid or uncertain classifications.
    """
    def invalid(reason):
        return parsed, 'invalid', {}, ['AI filename roles rejected: ' + reason]

    if not isinstance(roles, dict):
        return invalid('expected a role object')
    title = roles.get('title_text')
    authors = roles.get('author_texts')
    circle = roles.get('circle_text', '')
    notes = roles.get('annotation_texts', [])
    language = roles.get('title_language')
    if language is not None and (not isinstance(language, str) or language not in {'zh', 'ja', 'ko', 'en', 'unknown'}):
        return invalid('title_language must be zh, ja, ko, en, or unknown')
    if (not isinstance(title, str) or not isinstance(authors, list) or not isinstance(circle, str)
            or not isinstance(notes, list) or not all(isinstance(x, str) for x in authors + notes)):
        return invalid('title, authors, circle, or annotations have invalid types')
    title, circle = title.strip(), circle.strip()
    authors = list(dict.fromkeys(x.strip() for x in authors if x.strip()))
    notes = list(dict.fromkeys(x.strip() for x in notes if x.strip()))
    source = parsed.original_filename
    if any(text not in source for text in [title, circle] + authors + notes if text):
        return invalid('a quoted role is absent from the selected input')
    if any('[' in text or ']' in text for text in [title, circle] + authors):
        return invalid('roles must quote individual fields without metadata brackets')
    if title and not re.search(r'[^\W\d_]', title):
        return invalid('a numeric suffix or punctuation alone is not a title')
    if title and (title in authors or title == circle or title in notes or _is_annotation(title)):
        return invalid('the title is an author, circle, or annotation')
    if any(author in notes or _is_annotation(author) for author in authors):
        return invalid('an author is an annotation')
    if circle and (circle in notes or _is_annotation(circle)):
        return invalid('the circle is an annotation')
    if title:
        title_spans = [match.span() for match in re.finditer(re.escape(title), source)]
        # A role needs an occurrence outside the chosen title. This permits an
        # author's name inside a real title when the author is also listed
        # separately, while rejecting a whole "Author Title" string as title.
        for text in authors + notes + ([circle] if circle else []):
            spans = [match.span() for match in re.finditer(re.escape(text), source)]
            if not any(end <= start_title or start >= end_title
                       for start, end in spans for start_title, end_title in title_spans):
                return invalid('the title overlaps an assigned metadata field')
    if parsed.author_candidate_kind == 'circle_author':
        if not set(parsed.creators).issubset(authors) or (circle and circle != parsed.circle):
            return invalid('roles conflict with explicit Circle(Author) evidence')
        if title in parsed.creators or (title and title == parsed.circle):
            return invalid('the title repeats explicit author/circle evidence')
    plausible_brackets = [text for text in re.findall(r'\[([^\]]*)\]', source)
                          if not _is_annotation(text.strip()) and '(' not in text]
    if (title and not (parsed.original_title or parsed.translated_title) and title in parsed.creators
            and len(plausible_brackets) <= 1):
        return invalid('the only title quote is an unsupported author guess')

    # A narrower verbatim span may remove an author label, but a different
    # bracket cannot replace a clearly identified Chinese title.
    if parsed.translated_title and parsed.title_candidate_kind == 'unbracketed':
        if not title or title not in parsed.translated_title:
            return invalid('roles replace an explicit Chinese title')
    try:
        confidence = float(roles['confidence'])
        if isinstance(roles['confidence'], bool) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        return invalid('confidence must be a finite number from 0 to 1')
    if not isinstance(roles.get('uncertain'), bool):
        return invalid('uncertain must be a boolean')
    verified = {'title_text': title, 'author_texts': authors, 'circle_text': circle,
                'annotation_texts': notes, 'confidence': confidence, 'uncertain': roles['uncertain']}
    title_confidence = roles.get('title_confidence')
    if title_confidence is not None:
        if (isinstance(title_confidence, bool) or not isinstance(title_confidence, (int, float))
                or not math.isfinite(title_confidence) or not 0 <= title_confidence <= 1):
            return invalid('title_confidence must be a finite number from 0 to 1')
        verified['title_confidence'] = title_confidence
    if language is not None:
        verified['title_language'] = language
    if language == 'ja' and parsed.title_language_hint == 'zh':
        return invalid('Japanese classification conflicts with a separate Chinese title')
    if language == 'zh' and HIRAGANA_KATAKANA_RE.search(title):
        return invalid('Chinese classification conflicts with Japanese kana')
    if language == 'unknown' and HAN_RE.search(title) and not HIRAGANA_KATAKANA_RE.search(title):
        return parsed, 'uncertain', verified, ['The source title uses Han characters and its language could not be determined; automatic writing is skipped.']
    uncertain_roles = roles['uncertain'] or confidence < 0.8
    title_only = (uncertain_roles and title_confidence is not None and title_confidence >= 0.85
                  and parsed.title_candidate_kind == 'unbracketed'
                  and title == (parsed.translated_title or parsed.original_title)
                  and language in {'zh', 'ja', 'ko', 'en'})
    if uncertain_roles and not title_only:
        return parsed, 'uncertain', verified, ['AI could not confidently distinguish filename roles; automatic writing is skipped.']

    selected = parse_filename(title)
    # A quoted title may omit separate [Vol. 2]/[Ch. 15] fields. Retain only
    # numbering already attached to this literal title by deterministic rules.
    if title and title in (parsed.translated_title or parsed.original_title):
        if not (selected.volume or selected.volume_range):
            selected = replace(selected, volume=parsed.volume, volume_range=parsed.volume_range)
        if not (selected.chapter or selected.chapter_range):
            selected = replace(selected, chapter=parsed.chapter, chapter_range=parsed.chapter_range)
    if selected.filename_suffix:
        title = re.sub(r'\s*' + re.escape(selected.filename_suffix) + r'$', '', title).rstrip()
    # Preserve the source string rather than reinterpreting parentheses inside
    # a title that has already been classified by the model.
    is_chinese = bool(HAN_RE.search(title)) and not HIRAGANA_KATAKANA_RE.search(title) and language not in {'ja', 'ko', 'en'}
    original = parsed.original_title if is_chinese and parsed.translated_title else ('' if is_chinese else title)
    resolved = replace(parsed, original_title=original,
                       translated_title=title if is_chinese else '', creators=[] if title_only else authors,
                       title_language_hint=language or selected.title_language_hint,
                       circle=circle or parsed.circle, series=selected.series, volume=selected.volume,
                       chapter=selected.chapter, volume_range=selected.volume_range, chapter_range=selected.chapter_range,
                       title_candidate_kind='ai_quoted', author_candidate_kind='ai_quoted',
                       confidence=title_confidence if title_only else confidence,
                       review_required=title_only or bool(parsed.filename_suffix),
                       evidence=parsed.evidence + ['ai-role-title: ' + title, 'ai-role-authors: ' + ', '.join(authors)])
    return (resolved, 'title_only', verified,
            ['Title identification is confident, but other roles are uncertain; only title and filename Comments are eligible for automatic writing.']) if title_only else (resolved, 'accepted', verified, [])
