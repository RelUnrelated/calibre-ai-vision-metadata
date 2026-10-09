"""Safety-first calibre metadata application helpers."""

from __future__ import annotations

import datetime
import copy
import math
from html import escape
import json
import re
from typing import Any


AUDIT_KEY = "ai_vision_metadata.audit"
MANUAL_FIELDS = {'tags', 'publisher', 'pubdate', 'identifiers'}
FILENAME_COMMENT_SOURCES = {'custom_column', 'analysis_history', 'existing_title_snapshot'}


def capture_filename_comments(db: Any, book_id: int, source: dict[str, Any], mi: Any) -> dict[str, Any]:
    """Capture input text on the GUI thread, before the title can be replaced.

    Old releases kept the pre-write title in their audit record even when they
    skipped Comments. Recover that text rather than archiving a translated title
    on the next run. A calibre directory is never a filename backup.
    """
    text, origin = '', 'unavailable'
    if source.get('original_filename_source') == 'custom_column':
        text, origin = source.get('original_filename') or '', 'custom_column'
    else:
        try:
            saved = db.get_custom_book_data(AUDIT_KEY, (book_id,)).get(book_id)
            record = json.loads(saved) if isinstance(saved, str) else saved
            if isinstance(record, dict) and record.get('book_id') == book_id:
                if record.get('comments_source') in FILENAME_COMMENT_SOURCES:
                    text = record.get('comments')
                elif record.get('original_filename_source') == 'custom_column':
                    text = record.get('original_filename')
                if not text and isinstance(record.get('original_values'), dict):
                    text = record['original_values'].get('title')
                if isinstance(text, str) and text.strip():
                    origin = 'analysis_history'
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        if not isinstance(text, str) or not text.strip():
            text, origin = getattr(mi, 'title', '') or '', 'existing_title_snapshot'
    if not isinstance(text, str) or not text.strip() or text.strip().casefold() in {'unknown', '未知', '未知书名'}:
        text, origin = '', 'unavailable'
    return {'text': text, 'source': origin,
            'write_allowed': bool(text) and (origin == 'custom_column' or not (getattr(mi, 'comments', '') or '').strip())}


def validate_manual_fields(approved_data: dict[str, Any]) -> None:
    """Validate explicit review input before making any database changes."""
    for key in MANUAL_FIELDS:
        field = approved_data.get(key)
        if not isinstance(field, dict) or field.get('manual') is not True:
            continue
        value = str(field.get('value') or '').strip()
        if not value:
            continue
        if key == 'pubdate':
            try:
                date = datetime.datetime.strptime(value, '%Y-%m-%d')
                if date.strftime('%Y-%m-%d') != value:
                    raise ValueError
            except ValueError:
                raise ValueError('Publication date must be a valid date in YYYY-MM-DD format.') from None
        elif key == 'identifiers':
            for pair in value.split(','):
                identifier, separator, content = pair.strip().partition(':')
                if not separator or not identifier.strip() or not content.strip():
                    raise ValueError('Identifiers must use type:value pairs, separated by commas (for example isbn:123).')


def _json_value(value: Any):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(x) for x in value]
    if isinstance(value, list):
        return [_json_value(x) for x in value]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    return value


def snapshot_metadata(db: Any, book_id: int, fields: tuple[str, ...] = ()) -> dict[str, Any]:
    mi = db.get_metadata(book_id)
    selected = fields or ("title", "authors", "series", "series_index", "publisher", "pubdate", "tags", "comments", "languages", "identifiers")
    values = {}
    for field in selected:
        value = getattr(mi, field, None)
        if isinstance(value, (list, tuple)):
            value = list(value)
        elif isinstance(value, dict):
            value = dict(value)
        values[field] = value
    if '#original_filename' in getattr(db, 'field_metadata', {}):
        values['#original_filename'] = db.field_for('#original_filename', book_id, '')
    return {"library_id": getattr(db, "library_id", None), "book_id": book_id, "values": values}


def _value_action(approved_data: dict[str, Any], key: str):
    data = approved_data.get(key)
    if data is None:
        return None, None
    if isinstance(data, dict):
        return data.get("value"), data.get("action", "overwrite")
    return data, "overwrite"


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [x.strip() for x in re.split(r'\s*(?:&|,|，|、)\s*', value) if x.strip()]
    return [str(x).strip() for x in (value or []) if str(x).strip()]


def prepare_automatic_update(metadata: dict[str, Any]) -> dict[str, Any]:
    """Map a successful analysis to nonempty automatic-write fields only."""
    if metadata.get('filename_role_status') in {'invalid', 'uncertain'}:
        return {}
    if metadata.get('translation_status') == 'needs_translation':
        return {}
    title = str(metadata.get('title') or '').strip()
    if not title:
        return {}
    approved = {'title': {'value': title, 'action': 'overwrite'}}
    for source, target in ([] if metadata.get('title_only') else [('creators', 'authors'), ('languages', 'languages')]):
        value = metadata.get(source)
        if value:
            approved[target] = {'value': value, 'action': 'overwrite'}
    if metadata.get('comments_source') in FILENAME_COMMENT_SOURCES:
        if metadata.get('comments') and metadata.get('comments_write_allowed'):
            approved['comments'] = {'value': metadata['comments'], 'action': 'overwrite'}
    elif metadata.get('original_filename_source') == 'custom_column' and metadata.get('original_filename'):
        approved['comments'] = {'value': metadata['original_filename'], 'action': 'overwrite'}
    if metadata.get('series') and not metadata.get('title_only'):
        volume = str(metadata.get('volume') or '').strip()
        issue = str(metadata.get('issue_number') or '').strip()
        index = f'{volume}.{issue.zfill(2)}' if volume.isdigit() and issue.isdigit() else (issue or volume)
        try:
            numeric = float(index)
            if math.isfinite(numeric) and numeric >= 0:
                approved['series'] = {'value': metadata['series'], 'action': 'overwrite'}
                approved['series_index'] = {'value': index, 'action': 'overwrite'}
        except (TypeError, ValueError):
            pass
    approved['_analysis_record'] = dict(metadata, write_mode='automatic')
    return approved


def apply_metadata_safely(db: Any, book_id: int, approved_data: dict[str, Any], snapshot: dict[str, Any] | None = None,
                          expected_library_id: str | None = None) -> dict[str, Any]:
    """Apply only approved fields and reject stale/cross-library writes."""
    if expected_library_id is not None and getattr(db, "library_id", None) != expected_library_id:
        return {"status": "conflict", "reason": "library_changed"}
    if not db.has_id(book_id):
        return {"status": "conflict", "reason": "book_missing"}
    if snapshot and (snapshot.get('library_id') != getattr(db, 'library_id', None) or snapshot.get('book_id') != book_id):
        return {"status": "conflict", "reason": "snapshot_mismatch"}

    current_metadata = db.get_metadata(book_id)
    mi = current_metadata.deepcopy() if hasattr(current_metadata, 'deepcopy') else copy.deepcopy(current_metadata)
    if snapshot and snapshot.get("library_id") == getattr(db, "library_id", None):
        for field, old_value in snapshot.get("values", {}).items():
            current = db.field_for(field, book_id, '') if field.startswith('#') else getattr(mi, field, None)
            if isinstance(current, tuple):
                current = list(current)
            if current != old_value:
                return {"status": "conflict", "reason": "field_changed", "field": field}

    original_values = {}
    for field in ("title", "authors", "series", "series_index", "publisher", "pubdate", "tags", "comments", "languages", "identifiers"):
        value = getattr(mi, field, None)
        original_values[field] = _json_value(value)

    writable_fields = {'title', 'authors', 'series', 'series_index', 'comments', 'languages'}
    writable_fields.update(key for key in MANUAL_FIELDS
                           if isinstance(approved_data.get(key), dict) and approved_data[key].get('manual') is True
                           and str(approved_data[key].get('value') or '').strip())
    approved_data = {key: value for key, value in approved_data.items() if key in writable_fields or key == '_analysis_record'}
    try:
        validate_manual_fields(approved_data)
    except ValueError as error:
        return {'status': 'conflict', 'reason': str(error)}
    if not any(key in writable_fields for key in approved_data):
        return {"status": "unchanged", "book_id": book_id}

    val, action = _value_action(approved_data, "languages")
    if val:
        incoming = _as_list(val)
        mi.languages = list(dict.fromkeys((list(mi.languages or []) + incoming) if action == "append" else incoming))

    val, action = _value_action(approved_data, "title")
    if val:
        mi.title = f"{mi.title} {val}".strip() if action == "append" and mi.title else str(val).strip()
        from calibre.ebooks.metadata import title_sort
        mi.title_sort = title_sort(mi.title, lang=mi.languages[0] if mi.languages else None)

    val, action = _value_action(approved_data, "authors")
    if val:
        incoming = _as_list(val)
        mi.authors = list(dict.fromkeys((list(mi.authors or []) + incoming) if action == "append" else incoming))
        from calibre.ebooks.metadata import authors_to_sort_string
        mi.author_sort = authors_to_sort_string(mi.authors)

    val, _ = _value_action(approved_data, "series")
    if val:
        mi.series = str(val).strip()
    val, _ = _value_action(approved_data, "series_index")
    if val not in (None, ''):
        try:
            mi.series_index = float(val)
            if not math.isfinite(mi.series_index) or mi.series_index < 0:
                raise ValueError
        except (TypeError, ValueError):
            return {"status": "conflict", "reason": "invalid_series_index"}

    val, action = _value_action(approved_data, 'comments')
    if val:
        old = mi.comments or ''
        # calibre renders Comments as HTML; preserve literal filename markup.
        text = escape(str(val)).replace('\n', '<br>')
        mi.comments = f'{old}<br><br>{text}' if action == 'append' and old.strip() else text

    val, action = _value_action(approved_data, 'tags')
    if val:
        incoming = _as_list(val)
        mi.tags = list(dict.fromkeys((list(mi.tags or []) + incoming) if action == 'append' else incoming))
    val, _ = _value_action(approved_data, 'publisher')
    if val:
        mi.publisher = str(val).strip()
    val, _ = _value_action(approved_data, 'pubdate')
    if val:
        mi.pubdate = datetime.datetime.strptime(str(val).strip(), '%Y-%m-%d')
    val, action = _value_action(approved_data, 'identifiers')
    if val:
        identifiers = dict(mi.identifiers or {}) if action == 'append' else {}
        for pair in str(val).split(','):
            key, value = pair.strip().split(':', 1)
            identifiers[key.strip().lower()] = value.strip()
        mi.identifiers = identifiers

    db.set_metadata(book_id, mi)

    # Store exact source text and an audit record through calibre's API. This is
    # not direct SQLite access and works even when optional custom columns exist
    # under different labels.
    record = approved_data.get("_analysis_record")
    if record:
        payload = dict(record)
        payload.update({"book_id": book_id, "written_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "original_values": original_values, "approved_data": approved_data})
        db.add_custom_book_data(AUDIT_KEY, {book_id: json.dumps(_json_value(payload), ensure_ascii=False)})
    return {"status": "written", "book_id": book_id}
