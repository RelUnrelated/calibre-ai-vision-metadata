import datetime
import json
import unittest
from types import SimpleNamespace

from metadata_writer import apply_metadata_safely, snapshot_metadata, prepare_automatic_update, capture_filename_comments
from result_schema import normalize_result


class FakeDB:
    library_id = "library-a"

    def __init__(self):
        self.saved = None
        self.audit = None
        self.mi = SimpleNamespace(
            title="原有标题", authors=["作者"], series="", series_index=1.0,
            publisher="", pubdate=datetime.datetime(2020, 1, 1), tags=["人工标签"],
            comments="原有说明", languages=["jpn"], identifiers={}
        )

    def get_metadata(self, book_id):
        return self.mi

    def has_id(self, book_id):
        return book_id == 1

    def set_metadata(self, book_id, mi):
        self.saved = book_id
        self.mi = mi

    def add_custom_book_data(self, key, values):
        self.audit = (key, values)


class MetadataWriterTests(unittest.TestCase):
    def test_empty_comments_preserve_complete_title_before_replacement(self):
        db = FakeDB()
        db.mi.title = ' [作者][汉化组]日本語の作品2 <DL> & extra.cbz '
        db.mi.comments = None
        source = {'original_filename': '截断目录', 'original_filename_source': 'calibre_path_fallback'}
        captured = capture_filename_comments(db, 1, source, db.mi)
        result = normalize_result({'title': '中文译名2', 'comments': 'AI摘要'}, source['original_filename'],
                                  existing_title=db.mi.title, filename_source='calibre_path_fallback',
                                  comments_context=captured)
        update = prepare_automatic_update(result)
        self.assertEqual(update['comments']['value'], db.mi.title)
        self.assertEqual(result['comments_source'], 'existing_title_snapshot')
        self.assertNotIn('截断目录', result['comments'])

    def test_history_recovers_source_after_older_version_changed_title(self):
        db = FakeDB()
        db.mi.title = '新的中文译名 2'
        db.mi.comments = ''
        original = '[作者][汉化组]日本語の作品2.cbz'
        source = {'original_filename': '新的中文译名 2', 'original_filename_source': 'calibre_path_fallback'}
        for record in (
            {'book_id': 1, 'original_filename_source': 'calibre_path_fallback', 'original_filename': '截断目录',
             'original_values': {'title': original}},
            {'book_id': 1, 'comments_source': 'existing_title_snapshot', 'comments': original,
             'original_values': {'title': '新的中文译名 2'}},
            {'book_id': 1, 'original_filename_source': 'custom_column', 'original_filename': original},
        ):
            with self.subTest(record=record):
                db.get_custom_book_data = lambda *args: {1: json.dumps(record)}
                captured = capture_filename_comments(db, 1, source, db.mi)
                self.assertEqual(captured, {'text': original, 'source': 'analysis_history', 'write_allowed': True})

    def test_custom_source_has_priority_and_preserves_exact_text(self):
        db = FakeDB()
        original = ' 完整原始文件名 <DL> & 内容.cbz '
        captured = capture_filename_comments(db, 1, {'original_filename': original,
                                            'original_filename_source': 'custom_column'}, db.mi)
        self.assertEqual(captured, {'text': original, 'source': 'custom_column', 'write_allowed': True})

    def test_invalid_or_foreign_history_uses_current_snapshot(self):
        db = FakeDB()
        db.mi.comments = None
        for record in ('bad json', '[]', json.dumps({'book_id': 2, 'original_values': {'title': '另一书籍'}})):
            with self.subTest(record=record):
                db.get_custom_book_data = lambda *args: {1: record}
                captured = capture_filename_comments(db, 1, {}, db.mi)
                self.assertEqual(captured['text'], db.mi.title)
                self.assertEqual(captured['source'], 'existing_title_snapshot')

    def test_fallback_backup_does_not_overwrite_existing_comments(self):
        db = FakeDB()
        captured = capture_filename_comments(db, 1, {}, db.mi)
        self.assertFalse(captured['write_allowed'])
        result = normalize_result({}, '目录名', filename_source='calibre_path_fallback',
                                  existing_title=db.mi.title, comments_context=captured)
        self.assertNotIn('comments', prepare_automatic_update(result))

    def test_automatic_update_uses_nonempty_fields_and_ignores_manual_only_fields(self):
        result = prepare_automatic_update({'title': '书名2', 'creators': ['作者'], 'series': '书名', 'volume': '2',
                                          'languages': ['zho'], 'original_filename': '完整原始文件名.cbz',
                                          'original_filename_source': 'custom_column', 'tags': ['AI标签'],
                                          'publisher': 'AI出版社', 'pubdate': '2026-01-01', 'ids': 'ai:123',
                                          'review_required': True})
        self.assertEqual(result['title']['value'], '书名2')
        self.assertEqual(result['series_index']['value'], '2')
        self.assertEqual(result['comments']['value'], '完整原始文件名.cbz')
        self.assertEqual(result['_analysis_record']['write_mode'], 'automatic')
        for field in ('tags', 'publisher', 'pubdate', 'identifiers', 'original_filename'):
            self.assertNotIn(field, result)

    def test_automatic_update_without_title_is_skipped(self):
        self.assertEqual(prepare_automatic_update({'title': '', 'creators': ['作者']}), {})

    def test_automatic_update_without_volume_does_not_set_series(self):
        result = prepare_automatic_update({'title': '单行本', 'series': '单行本', 'volume': ''})
        self.assertNotIn('series', result)
        self.assertNotIn('series_index', result)

    def test_automatic_update_rejects_invalid_series_index(self):
        for volume in ('bad', 'nan', 'inf', '-1'):
            with self.subTest(volume=volume):
                result = prepare_automatic_update({'title': '书名', 'series': '丛书', 'volume': volume})
                self.assertNotIn('series', result)
                self.assertNotIn('series_index', result)

    def test_automatic_update_preserves_comments_when_only_directory_fallback_exists(self):
        result = prepare_automatic_update({'title': '书名', 'original_filename': '目录名',
                                          'original_filename_source': 'calibre_path_fallback'})
        self.assertNotIn('comments', result)
    def test_conflict_does_not_write(self):
        db = FakeDB()
        snap = snapshot_metadata(db, 1)
        db.mi.title = "用户刚刚修改的标题"
        result = apply_metadata_safely(db, 1, {"title": {"value": "AI 标题"}}, snap, "library-a")
        self.assertEqual(result["status"], "conflict")
        self.assertIsNone(db.saved)

    def test_comments_preserve_manual_tags_and_record_audit(self):
        db = FakeDB()
        snap = snapshot_metadata(db, 1)
        result = apply_metadata_safely(
            db, 1,
            {
                "tags": {"value": "新标签", "action": "append"},
                "comments": {"value": "[组] 标题.cbz", "action": "overwrite"},
                "_analysis_record": {"original_filename": "[组] 标题.cbz"},
            },
            snap,
            "library-a",
        )
        self.assertEqual(result["status"], "written")
        self.assertEqual(db.mi.tags, ["人工标签"])
        self.assertEqual(db.mi.comments, "[组] 标题.cbz")
        self.assertIsNotNone(db.audit)

    def test_snapshot_from_another_library_or_book_is_rejected(self):
        for key, value in [('library_id', 'library-b'), ('book_id', 2)]:
            with self.subTest(key=key):
                db = FakeDB()
                snap = snapshot_metadata(db, 1)
                snap[key] = value
                result = apply_metadata_safely(db, 1, {'comments': 'new'}, snap)
                self.assertEqual(result['status'], 'conflict')
                self.assertIsNone(db.saved)

    def test_ai_only_fields_cannot_be_written_without_manual_confirmation(self):
        db = FakeDB()
        result = apply_metadata_safely(db, 1, {'tags': 'AI tag', 'publisher': 'AI publisher',
                                               'pubdate': '2026-01-01', 'identifiers': 'isbn:123'})
        self.assertEqual(result['status'], 'unchanged')
        self.assertIsNone(db.saved)

    def test_manual_review_fields_are_written(self):
        db = FakeDB()
        approved = {key: {'value': value, 'action': 'overwrite', 'manual': True} for key, value in {
            'tags': '人工新标签', 'publisher': '人工出版社', 'pubdate': '2026-10-09',
            'identifiers': 'custom:abc, url:https://example.test/book'
        }.items()}
        result = apply_metadata_safely(db, 1, approved, snapshot_metadata(db, 1), db.library_id)
        self.assertEqual(result['status'], 'written')
        self.assertEqual(db.mi.tags, ['人工新标签'])
        self.assertEqual(db.mi.publisher, '人工出版社')
        self.assertEqual(db.mi.pubdate, datetime.datetime(2026, 10, 9))
        self.assertEqual(db.mi.identifiers['url'], 'https://example.test/book')

    def test_manual_tags_and_identifiers_can_merge(self):
        db = FakeDB()
        db.mi.identifiers = {'old': 'kept'}
        apply_metadata_safely(db, 1, {'tags': {'value': '新标签, 人工标签', 'action': 'append', 'manual': True},
                                     'identifiers': {'value': 'new:added', 'action': 'append', 'manual': True}})
        self.assertEqual(db.mi.tags, ['人工标签', '新标签'])
        self.assertEqual(db.mi.identifiers, {'old': 'kept', 'new': 'added'})

    def test_invalid_manual_input_does_not_partially_write(self):
        for key, value in [('pubdate', '2026-02-30'), ('pubdate', '2026-1-1'), ('identifiers', 'no-colon'),
                           ('identifiers', 'isbn:'), ('identifiers', ':123')]:
            with self.subTest(key=key, value=value):
                db = FakeDB()
                approved = {key: {'value': value, 'manual': True}, 'comments': 'new'}
                result = apply_metadata_safely(db, 1, approved)
                self.assertEqual(result['status'], 'conflict')
                self.assertIsNone(db.saved)
                self.assertEqual(db.mi.comments, '原有说明')

    def test_empty_manual_fields_preserve_existing_metadata(self):
        db = FakeDB()
        approved = {key: {'value': '', 'manual': True} for key in ('tags', 'publisher', 'pubdate', 'identifiers')}
        result = apply_metadata_safely(db, 1, approved)
        self.assertEqual(result['status'], 'unchanged')
        self.assertIsNone(db.saved)

    def test_invalid_index_does_not_mutate_cached_metadata(self):
        for index in ('bad', 'nan', 'inf', '-1'):
            with self.subTest(index=index):
                db = FakeDB()
                result = apply_metadata_safely(db, 1, {'series': 'new', 'series_index': index})
                self.assertEqual(result['status'], 'conflict')
                self.assertEqual(db.mi.series, '')
                self.assertIsNone(db.saved)

    def test_changed_original_filename_blocks_write(self):
        db = FakeDB()
        db.field_metadata = {'#original_filename': {}}
        db.original = 'original.cbz'
        db.field_for = lambda *args: db.original
        snap = snapshot_metadata(db, 1)
        db.original = 'user-edit.cbz'
        result = apply_metadata_safely(db, 1, {'comments': 'new'}, snap)
        self.assertEqual(result['field'], '#original_filename')
        self.assertIsNone(db.saved)

    def test_filename_markup_is_literal_in_comments(self):
        db = FakeDB()
        apply_metadata_safely(db, 1, {'comments': '<DL> A & B.cbz'})
        self.assertEqual(db.mi.comments, '&lt;DL&gt; A &amp; B.cbz')


if __name__ == "__main__":
    unittest.main()
