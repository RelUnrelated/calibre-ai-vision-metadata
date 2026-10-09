"""Run with calibre-debug -e tests/calibre_smoke.py and an isolated config dir.

Uses real Qt and calibre APIs, mocked provider HTTP responses, and disposable
libraries. Never opens the user's library or sends an external request.
"""
import importlib.util
from html import escape
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace, MethodType
import unittest
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qt.core import QApplication, QMessageBox, QFontDatabase, QFont
from calibre.db.legacy import LibraryDatabase
from calibre.ebooks.metadata.book.base import Metadata
from filename_parser import parse_filename
from metadata_writer import apply_metadata_safely, snapshot_metadata, prepare_automatic_update, AUDIT_KEY
from result_schema import normalize_result

# Load the working tree, not a possibly older installed plugin. Fake prefs keep
# provider settings and user keys completely out of this test process.
PACKAGE = 'calibre_plugins.ai_vision_metadata'
package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
config = ModuleType(PACKAGE + '.config')
config.prefs = {}
sys.modules[config.__name__] = config


def load_module(name):
    spec = importlib.util.spec_from_file_location(PACKAGE + '.' + name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    module._ = lambda text: text
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


main = load_module('main')
ui = load_module('ui')
APP = QApplication.instance() or QApplication([])
if os.environ.get('AI_METADATA_SMOKE_PREVIEW'):
    for font in ('segoeui.ttf', 'msyh.ttc'):
        path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / font
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    APP.setFont(QFont('Microsoft YaHei', 10))


def make_action(db):
    """Use actual queue methods with a minimal host and no modal UI."""
    main.prefs.setdefault('auto_apply_on_click', True)
    action = SimpleNamespace(batch_queue=[], queue_db=db, queue_library_id=db.library_id,
                             queue_active=False, pending_context={}, review_each=False,
                             active_book_id=None, batch_results=[], jobs=[], messages=[], refreshed=[], selected=[])
    model = SimpleNamespace(id=lambda row: row, refresh_ids=action.refreshed.extend)
    view = SimpleNamespace(model=lambda: model,
                           selectionModel=lambda: SimpleNamespace(selectedRows=lambda: action.selected))
    action.gui = SimpleNamespace(current_db=SimpleNamespace(new_api=db, library_path=''), library_view=view,
                                 job_manager=SimpleNamespace(run_threaded_job=action.jobs.append),
                                 status_bar=SimpleNamespace(showMessage=lambda message, timeout: action.messages.append(message)),
                                 job_exception=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('Unexpected modal error')))
    for name in ('identify_book', 'identify_books_with_review', 'start_analysis', 'process_next_in_queue',
                 'job_finished', 'run_api_request', 'apply_metadata', '_status_message', '_record_result',
                 '_result_summary', '_show_error_dialog'):
        setattr(action, name, MethodType(getattr(main.AIVisionAction, name), action))
    action.signals = SimpleNamespace(
        error_signal=SimpleNamespace(emit=action._show_error_dialog),
        review_signal=SimpleNamespace(emit=lambda *args: (_ for _ in ()).throw(AssertionError('Unexpected review dialog'))))
    return action


class CalibreSmokeTests(unittest.TestCase):
    def test_magazine_volume_is_removed_before_database_write_without_retry(self):
        original = '好きな子はいじめたくなるモノ'
        filename = '[テツナ]' + original + '(COMIC 阿吽 改 Vol.18)[中国翻译]'
        translated = '喜欢的孩子让人想要欺负'
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'choices': [{'message': {'content': json.dumps({
            'title': translated + ' 18', 'translated_title': translated + ' 18',
        })}}]}).encode()
        with patch('urllib.request.urlopen', return_value=response) as request:
            _, result, _, _ = main.AIVisionAction.run_api_request(None, 36, None, '', {
                'original_filename': filename, 'original_filename_source': 'custom_column'})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result['title'], translated)
        self.assertEqual(result['provider_title'], translated + ' 18')
        with tempfile.TemporaryDirectory(prefix='ai-metadata-publication-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                book_id = db.create_book_entry(Metadata('旧标题', ['旧作者']))
                approved = prepare_automatic_update(result)
                self.assertNotIn('series_index', approved)
                written = apply_metadata_safely(db, book_id, approved, snapshot_metadata(db, book_id), db.library_id)
                self.assertEqual(written['status'], 'written')
                self.assertEqual(db.get_metadata(book_id).title, translated)
            finally:
                library.close()

    def test_deepseek_fast_payload_and_optional_thinking(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                main.prefs.clear()
                main.prefs['ai_provider'] = 'DeepSeek'
                if enabled:
                    main.prefs['deepseek_thinking'] = True
                response = unittest.mock.MagicMock()
                response.__enter__.return_value.read.return_value = json.dumps({
                    'choices': [{'message': {'content': json.dumps({'title': '中文书名'})}}],
                    'usage': {'completion_tokens': 120, 'completion_tokens_details': {'reasoning_tokens': 0}},
                }).encode()
                with patch('urllib.request.urlopen', return_value=response) as request:
                    result = main.AIVisionAction.run_api_request(None, 1, None, '', {'original_filename': '中文书名'})
                payload = json.loads(request.call_args.args[0].data)
                self.assertEqual(payload['thinking']['type'], 'enabled' if enabled else 'disabled')
                self.assertEqual(payload['max_tokens'], 8192 if enabled else 2048)
                self.assertEqual(result[1]['request_metrics']['reasoning_tokens'], 0)
                widget = main.ConfigWidget()
                try:
                    self.assertEqual(widget.deepseek_thinking.isChecked(), enabled)
                    widget.save_settings()
                    self.assertEqual(main.prefs['deepseek_thinking'], enabled)
                finally:
                    widget.close()

    def test_title_only_uses_one_request_and_preserves_other_database_fields(self):
        original = 'お嬢样、调教される快乐に溺れる'
        translated = '大小姐，沉溺于被调教的快乐'
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'choices': [{'message': {'content': json.dumps({
            'title': translated, 'filename_roles': {
                'title_text': original, 'title_language': 'ja', 'title_confidence': 0.95,
                'author_texts': [], 'circle_text': '', 'annotation_texts': [], 'confidence': 0.6, 'uncertain': False,
            }})}}]}).encode()
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        with patch('urllib.request.urlopen', return_value=response) as request:
            _, result, _, _ = main.AIVisionAction.run_api_request(None, 386, None, '', {
                'original_filename': 'Truncated directory', 'existing_title': original,
                'original_filename_source': 'calibre_path_fallback'})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result['filename_role_status'], 'title_only')
        with tempfile.TemporaryDirectory(prefix='ai-metadata-title-only-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                book_id = db.create_book_entry(Metadata(original, ['人工作者']))
                db.set_field('series', {book_id: '人工系列'})
                db.set_field('series_index', {book_id: 42.0})
                written = apply_metadata_safely(db, book_id, prepare_automatic_update(result),
                                                snapshot_metadata(db, book_id), db.library_id)
                self.assertEqual(written['status'], 'written')
                mi = db.get_metadata(book_id)
                self.assertEqual(mi.title, translated)
                self.assertEqual(mi.authors, ['人工作者'])
                self.assertEqual(mi.series, '人工系列')
                self.assertEqual(mi.series_index, 42.0)
            finally:
                library.close()

    def test_reported_titles_get_one_correction_after_uncertain_roles(self):
        for original, translated in (
            ('乳首感度調查、はじめます', '乳头敏感度调查，开始了'),
            ('高飞车巨乳お嬢样と秘密のえっち', '与傲慢的巨乳大小姐的秘密性爱'),
        ):
            with self.subTest(original=original):
                context = {'original_filename': original, 'original_filename_source': 'custom_column',
                           'parsed_filename': parse_filename(original).as_dict()}
                main.prefs.clear()
                main.prefs['ai_provider'] = 'DeepSeek'
                roles = {'title_text': original, 'title_language': 'ja', 'author_texts': [],
                         'circle_text': '', 'annotation_texts': [], 'confidence': 0.95, 'uncertain': True}
                def response_for(value):
                    response = unittest.mock.MagicMock()
                    response.__enter__.return_value.read.return_value = json.dumps({
                        'choices': [{'message': {'content': json.dumps(value)}}]}).encode()
                    return response
                first = response_for({'title': original, 'filename_roles': roles})
                second = response_for({'title': translated, 'filename_roles': dict(roles, uncertain=False)})
                with patch('urllib.request.urlopen', side_effect=[first, second]) as request:
                    _, result, _, returned_context = main.AIVisionAction.run_api_request(None, 30, None, '', context)
                self.assertEqual(request.call_count, 2)
                self.assertEqual(result['title'], translated)
                self.assertEqual(result['filename_role_status'], 'accepted')
                self.assertEqual(result['request_metrics']['translation_repair_attempts'], 1)
                self.assertEqual(result['request_metrics']['request_attempts'], 2)
                self.assertEqual(returned_context, context)
                self.assertTrue(prepare_automatic_update(result))

    def test_untranslated_response_has_bounded_retry_and_visible_diagnostics(self):
        original = '乳首感度調查、はじめます'
        context = {'original_filename': original, 'original_filename_source': 'custom_column'}
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            'choices': [{'message': {'content': json.dumps({'title': original})}}]}).encode()
        with patch('urllib.request.urlopen', return_value=response) as request:
            _, result, _, _ = main.AIVisionAction.run_api_request(None, 30, None, '', context)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result['translation_status'], 'needs_translation')
        self.assertEqual(prepare_automatic_update(result), {})
        action = make_action(SimpleNamespace(library_id='test'))
        action._record_result(30, 'skipped', 'Japanese title was not translated', result)
        diagnostics = action.batch_results[0]['diagnostics']
        self.assertEqual(diagnostics['provider_title'], original)
        self.assertEqual(diagnostics['translation_status'], 'needs_translation')
        self.assertTrue(diagnostics['warnings'])

    def test_all_kanji_japanese_through_provider_and_review(self):
        filename = '[作者]放課後2[中国翻译]'
        context = {'original_filename': filename, 'original_filename_source': 'custom_column',
                   'existing_title': filename, 'parsed_filename': parse_filename(filename).as_dict()}
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        response = {'choices': [{'message': {'content': json.dumps({
            'title': '放学后2', 'filename_roles': {
                'title_text': '放課後2', 'title_language': 'ja', 'author_texts': ['作者'],
                'circle_text': '', 'annotation_texts': ['中国翻译'], 'confidence': 0.95, 'uncertain': False,
            }})}}]}
        mock_response = unittest.mock.MagicMock()
        mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
        with patch('urllib.request.urlopen', return_value=mock_response) as request:
            _, metadata, _, _ = main.AIVisionAction.run_api_request(None, 2, None, '', context)
        self.assertIn('filename_roles.title_language', json.dumps(json.loads(request.call_args.args[0].data)))
        self.assertIn('filename_roles.title_language', main.build_context_prompt('Saved custom prompt', context))
        self.assertEqual(metadata['original_title'], '放課後2')
        self.assertEqual(metadata['title'], '放学后 2')
        self.assertEqual(metadata['series'], '放学后')
        dialog = ui.MetadataReviewDialog(None, metadata, None)
        try:
            self.assertEqual(dialog.get_approved_data()['title']['value'], '放学后 2')
            self.assertIn('原文语言：日语', dialog.filename_details.text())
        finally:
            dialog.close()

    def test_kavita_numbering_in_real_database_and_review(self):
        with tempfile.TemporaryDirectory(prefix='ai-metadata-numbering-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                for marker, index in [('Vol. 7.5 ch015', 7.5), ('Vol. 1-5', 42.0), ('ch015', 42.0)]:
                    with self.subTest(marker=marker):
                        filename = '(C108)[社团(作者)]作品 ' + marker
                        book_id = db.create_book_entry(Metadata('旧标题', ['旧作者']))
                        db.set_field('series', {book_id: '原有系列'})
                        db.set_field('series_index', {book_id: 42.0})
                        normalized = normalize_result({}, filename)
                        dialog = ui.MetadataReviewDialog(None, normalized, None)
                        try:
                            approved = dialog.get_approved_data()
                            if marker.startswith('Vol. 7.5'):
                                self.assertEqual(approved['series_index']['value'], '7.5')
                                self.assertIn('章节：15', dialog.filename_details.text())
                            else:
                                self.assertEqual(approved['series_index']['value'], '')
                        finally:
                            dialog.close()
                        update = prepare_automatic_update(normalized)
                        written = apply_metadata_safely(db, book_id, update,
                                                        snapshot_metadata(db, book_id), db.library_id)
                        self.assertEqual(written['status'], 'written')
                        mi = db.get_metadata(book_id)
                        self.assertEqual(mi.series_index, index)
                        self.assertEqual(mi.series, '作品' if index == 7.5 else '原有系列')
                        self.assertEqual(mi.authors, ['作者'])
            finally:
                library.close()

    def test_ai_role_queue_corrects_author_and_skips_uncertain_or_invalid_results(self):
        with tempfile.TemporaryDirectory(prefix='ai-metadata-roles-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                title = '僕は誰と付き合えばいいのだろうか2'
                filenames = ['[' + title + '][悠木ヒロ][中国翻译]'] * 3
                ids = [db.create_book_entry(Metadata(filename, ['旧作者'])) for filename in filenames]
                action = make_action(db)
                action.gui.current_db.library_path = directory
                action.selected = ids
                main.prefs.clear()
                main.prefs['ai_provider'] = 'DeepSeek'
                def new_job(*args):
                    return SimpleNamespace(failed=False, args=args[3], callback=args[5])
                with patch('calibre.gui2.threaded_jobs.ThreadedJob', side_effect=new_job), \
                     patch.object(ui.MetadataReviewDialog, 'exec', side_effect=AssertionError('Unexpected review')):
                    action.identify_book()
                    for index, book_id in enumerate(ids):
                        role = {'title_text': title, 'author_texts': ['悠木ヒロ'], 'circle_text': '',
                                'annotation_texts': ['中国翻译'], 'confidence': 0.95, 'uncertain': index == 1}
                        if index == 2:
                            role['author_texts'] = ['臆造作者']
                        response = {'choices': [{'message': {'content': json.dumps({
                            'title': '模拟中文译名2', 'creators': ['错误的作者'], 'filename_roles': role,
                        })}}]}
                        mock_response = unittest.mock.MagicMock()
                        mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
                        job = action.jobs[index]
                        with patch('urllib.request.urlopen', return_value=mock_response) as request:
                            job.result = action.run_api_request(*job.args)
                            self.assertEqual(request.call_count, 2 if index == 1 else 1)
                            payload = json.loads(request.call_args.args[0].data)
                            prompt = payload['messages'][0]['content']
                            if isinstance(prompt, list):
                                prompt = '\n'.join(item.get('text', '') for item in prompt)
                            self.assertIn('filename_roles', prompt)
                            self.assertIn('author_texts', prompt)
                        if index == 0:
                            dialog = ui.MetadataReviewDialog(None, job.result[1], None)
                            try:
                                self.assertEqual(dialog.get_approved_data()['authors']['value'], '悠木ヒロ')
                                self.assertIn('AI 识别的原文标题：' + title, dialog.filename_details.text())
                            finally:
                                dialog.close()
                        job.callback(job)
                        APP.processEvents()
                    self.assertFalse(action.queue_active)
                    self.assertEqual([item['status'] for item in action.batch_results], ['written', 'skipped', 'skipped'])
                    self.assertEqual(action.batch_results[1]['reason'], 'filename_roles_uncertain')
                    self.assertEqual(action.batch_results[2]['reason'], 'filename_roles_invalid')
                    mi = db.get_metadata(ids[0])
                    self.assertEqual(mi.title, '模拟中文译名 2')
                    self.assertEqual(mi.authors, ['悠木ヒロ'])
                    self.assertEqual(mi.series, '模拟中文译名')
                    self.assertEqual(mi.series_index, 2.0)
                    self.assertEqual(mi.comments, filenames[0])
                    audit = json.loads(db.get_custom_book_data(AUDIT_KEY, (ids[0],))[ids[0]])
                    self.assertEqual(audit['filename_roles']['author_texts'], ['悠木ヒロ'])
                    self.assertEqual(audit['filename_role_status'], 'accepted')
                    for book_id in ids[1:]:
                        mi = db.get_metadata(book_id)
                        self.assertEqual(mi.title, filenames[0])
                        self.assertEqual(mi.authors, ['旧作者'])
                        self.assertFalse(mi.comments)
            finally:
                library.close()

    def test_reported_annotation_title_through_provider_and_review(self):
        original = '僕は谁と付き合えばいいのだろうか'
        filename = '[悠木ヒロ]' + original + '[中国翻译][禁漫去码]'
        context = {'original_filename': filename, 'original_filename_source': 'custom_column',
                   'existing_title': filename, 'parsed_filename': parse_filename(filename).as_dict()}
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        for proposed, expected in (('模拟中文译名', '模拟中文译名'), ('禁漫去码', original)):
            with self.subTest(proposed=proposed):
                response = {'choices': [{'message': {'content': json.dumps({'title': proposed})}}]}
                mock_response = unittest.mock.MagicMock()
                mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
                with patch('urllib.request.urlopen', return_value=mock_response):
                    _, metadata, _, _ = main.AIVisionAction.run_api_request(None, 2, None, '', context)
                self.assertEqual(metadata['original_title'], original)
                self.assertEqual(metadata['title'], expected)
                self.assertEqual(metadata['comments'], filename)
                self.assertEqual(metadata['creators'], ['悠木ヒロ'])
                dialog = ui.MetadataReviewDialog(None, metadata, None)
                try:
                    approved = dialog.get_approved_data()
                    self.assertEqual(approved['title']['value'], expected)
                    self.assertEqual(approved['comments']['value'], filename)
                finally:
                    dialog.close()

    def test_automatic_queue_preserves_filename_comments_and_recovers_legacy_history(self):
        with tempfile.TemporaryDirectory(prefix='ai-metadata-comments-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            library.new_api.create_custom_column('original_filename', 'Original filename', 'text', False)
            library.close()
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                filenames = ['[作者][汉化组]日本語の作品 <DL> & A2.cbz',
                             '[作者][汉化组]日本語の別冊2 [DL版].cbz',
                             '[作者][汉化组]日本語の続き2.cbz']
                ids = [db.create_book_entry(Metadata(title, ['原作者']))
                       for title in ('旧标题', filenames[1], '禁漫去码')]
                db.set_field('#original_filename', {ids[0]: filenames[0]})
                db.add_custom_book_data(AUDIT_KEY, {ids[2]: json.dumps({
                    'book_id': ids[2], 'original_filename_source': 'calibre_path_fallback',
                    'original_filename': '截断的目录名', 'original_values': {'title': filenames[2]},
                })})
                main.prefs.clear()
                main.prefs['ai_provider'] = 'DeepSeek'
                for _ in range(2):
                    # Reanalysis must retain the backup after the title changes.
                    db.set_field('comments', {book_id: None for book_id in ids})
                    action = make_action(db)
                    action.gui.current_db.library_path = directory
                    action.selected = ids
                    response = {'choices': [{'message': {'content': json.dumps({
                        'title': '模拟中文译名2', 'comments': '模型摘要不应写入',
                    })}}]}
                    mock_response = unittest.mock.MagicMock()
                    mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
                    def new_job(*args):
                        return SimpleNamespace(failed=False, args=args[3], callback=args[5])
                    with patch('calibre.gui2.threaded_jobs.ThreadedJob', side_effect=new_job), \
                         patch('urllib.request.urlopen', return_value=mock_response), \
                         patch.object(ui.MetadataReviewDialog, 'exec', side_effect=AssertionError('Unexpected review')):
                        action.identify_book()
                        for index, book_id in enumerate(ids):
                            job = action.jobs[index]
                            job.result = action.run_api_request(*job.args)
                            job.callback(job)
                            APP.processEvents()
                            self.assertEqual(db.get_metadata(book_id).comments, escape(filenames[index]))
                            self.assertEqual(db.get_metadata(book_id).title, '模拟中文译名 2')
                            self.assertEqual(db.field_for('#original_filename', book_id) or '',
                                             filenames[0] if index == 0 else '')
                        self.assertEqual([item['status'] for item in action.batch_results], ['written'] * 3)
                        self.assertFalse(action.queue_active)
            finally:
                library.close()

    def test_automatic_volume_write_uses_formatted_title_and_matching_series(self):
        with tempfile.TemporaryDirectory(prefix='ai-metadata-volume-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                for filename, raw in (
                    ('直到紫藤花盛开2 [汉化组]', {'series': '错误丛书'}),
                    ('[作者]日本語の作品 第2巻', {'title': '直到紫藤花盛开 第9卷', 'series': '另一译名9'}),
                ):
                    with self.subTest(filename=filename):
                        book_id = db.create_book_entry(Metadata('旧标题', ['旧作者']))
                        snap = snapshot_metadata(db, book_id)
                        normalized = normalize_result(raw, filename)
                        update = prepare_automatic_update(normalized)
                        written = apply_metadata_safely(db, book_id, update, snap, db.library_id)
                        self.assertEqual(written['status'], 'written')
                        mi = db.get_metadata(book_id)
                        self.assertEqual(mi.title, '直到紫藤花盛开 2')
                        self.assertEqual(mi.series, '直到紫藤花盛开')
                        self.assertEqual(mi.series_index, 2.0)
            finally:
                library.close()

    def test_automatic_queue_writes_continues_after_failures_and_never_opens_dialogs(self):
        with tempfile.TemporaryDirectory(prefix='ai-metadata-auto-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                filenames = ['[作者][汉化组]作品の第一話', '[作者]作品の続き', '[作者][汉化组]',
                             '[作者]作品の別冊', '[作者][汉化组]作品の最終話']
                ids = [db.create_book_entry(Metadata(name, ['原作者'])) for name in filenames]
                db.set_field('comments', {book_id: '原有简介' for book_id in ids})
                db.set_field('tags', {book_id: ['人工标签'] for book_id in ids})
                db.set_field('publisher', {book_id: '人工出版社' for book_id in ids})
                db.set_field('identifiers', {book_id: {'manual': 'keep'} for book_id in ids})
                action = make_action(db)
                action.gui.current_db.library_path = directory
                action.selected = ids
                main.prefs.clear()
                main.prefs['ai_provider'] = 'DeepSeek'
                def new_job(*args):
                    return SimpleNamespace(failed=False, args=args[3], callback=args[5])
                with patch('calibre.gui2.threaded_jobs.ThreadedJob', side_effect=new_job), \
                     patch.object(main.QMessageBox, 'information', side_effect=AssertionError('Unexpected confirmation')), \
                     patch.object(ui.MetadataReviewDialog, 'exec', side_effect=AssertionError('Unexpected review')):
                    action.identify_book()
                    self.assertEqual(len(action.jobs), 1)
                    action.identify_book()  # Reentry must not replace the running queue.
                    self.assertEqual(len(action.jobs), 1)
                    for index, book_id in enumerate(ids):
                        self.assertEqual(len(action.jobs), index + 1)
                        job = action.jobs[index]
                        if index == 1:
                            job.failed = True
                            job.exception = RuntimeError('simulated worker failure')
                        else:
                            title = '中文译名甲' if index == 0 else '中文译名乙'
                            raw = {'title': title, 'series': title, 'creators': ['作者'], 'tags': ['AI标签'],
                                   'publisher': 'AI出版社', 'ids': 'ai:bad', 'pub_year': 2026}
                            response = {'choices': [{'message': {'content': json.dumps(raw)}}]}
                            mock_response = unittest.mock.MagicMock()
                            mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
                            with patch('urllib.request.urlopen', return_value=mock_response):
                                job.result = action.run_api_request(*job.args)
                            if index == 2:
                                self.assertEqual(job.result[1]['title'], '', job.result)
                            if index == 3:
                                db.set_field('comments', {book_id: '用户在分析期间修改的简介'})
                        job.callback(job)
                        APP.processEvents()
                    self.assertFalse(action.queue_active)
                    self.assertEqual(action.batch_queue, [])
                    self.assertEqual(action.pending_context, {})
                    self.assertEqual([r['status'] for r in action.batch_results],
                                     ['written', 'skipped', 'skipped', 'skipped', 'written'])
                    self.assertEqual(db.get_metadata(ids[0]).title, '中文译名甲')
                    self.assertEqual(db.get_metadata(ids[4]).title, '中文译名乙')
                    for index in (1, 2, 3):
                        self.assertEqual(db.get_metadata(ids[index]).title, filenames[index])
                    self.assertEqual(db.get_metadata(ids[3]).comments, '用户在分析期间修改的简介')
                    for book_id in (ids[0], ids[4]):
                        mi = db.get_metadata(book_id)
                        self.assertFalse(mi.series)
                        self.assertEqual(mi.comments, '原有简介')
                        self.assertEqual(mi.tags, ['人工标签'])
                        self.assertEqual(mi.publisher, '人工出版社')
                        self.assertEqual(mi.identifiers, {'manual': 'keep'})
                    self.assertIn('分析完成：写入 2 本，跳过 3 本。', action.messages[-1])
                    self.assertEqual(action.batch_results[0]['request_metrics']['request_attempts'], 1)
            finally:
                library.close()

    def test_automatic_errors_use_status_instead_of_modal_dialog(self):
        action = make_action(SimpleNamespace(library_id='A'))
        with patch('calibre.gui2.error_dialog', side_effect=AssertionError('Unexpected modal error')):
            action._show_error_dialog('simulated error')
        self.assertEqual(action.messages, ['simulated error'])

    def test_timing_report_includes_retries_and_response_length(self):
        import io
        import urllib.error
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        response = {'choices': [{'message': {'content': '{"title":"书名"}'}}], 'usage': {'completion_tokens': 12}}
        mock_response = unittest.mock.MagicMock()
        mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
        errors = [urllib.error.HTTPError('https://example.test', code, 'retry', {}, io.BytesIO(b'{}'))
                  for code in (429, 503)]
        with patch('urllib.request.urlopen', side_effect=errors + [mock_response]), patch('time.sleep') as sleep:
            result = main.AIVisionAction.run_api_request(None, 1, None, '', {'original_filename': '书名'})
        metrics = result[1]['request_metrics']
        self.assertEqual(metrics['request_attempts'], 3)
        self.assertEqual(metrics['retry_wait_seconds'], 6)
        self.assertEqual(len(metrics['attempt_timings']), 3)
        self.assertEqual(metrics['response_characters'], len('{"title":"书名"}'))
        self.assertEqual(metrics['output_tokens'], 12)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [2, 4])

    def test_reported_deepseek_format_preamble_reaches_review(self):
        prefix = '[剥元ここ][禁漫汉化组](C108)[うずらフロンティア(剥元ここ)]'
        context = {'original_filename': prefix, 'existing_title': prefix + '娘が通勤用オナホになっちゃうまで 前日譚[中国翻译]',
                   'original_filename_source': 'calibre_path_fallback'}
        title = '像天敌般的小丫头变成通勤用飞机杯为止 前日谭'
        raw = '{"type": "json_object"}\n' + json.dumps({'series': title, 'volume': '', 'issue_number': '',
                                                             'title': title, 'creators': ['剥元ここ']}, ensure_ascii=False)
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        response = {'choices': [{'message': {'content': raw}}]}
        mock_response = unittest.mock.MagicMock()
        mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
        with patch('urllib.request.urlopen', return_value=mock_response):
            result = main.AIVisionAction.run_api_request(None, 2, None, '', context)
        self.assertIsInstance(result, tuple, result)
        self.assertEqual(result[1]['title'], title)
        dialog = ui.MetadataReviewDialog(None, result[1], None)
        try:
            self.assertEqual(dialog.results['title']['widget'].text(), title)
            self.assertEqual(dialog.results['authors']['widget'].text(), '剥元ここ')
            self.assertFalse(result[1]['cover_image_supplied'])
        finally:
            dialog.close()

    def test_deepseek_prompt_is_independent_and_key_is_preserved(self):
        main.prefs.clear()
        main.prefs.update({'ai_provider': 'DeepSeek', 'api_key_deepseek': 'TEST-ONLY-KEY',
                           'prompt_openai': 'OpenAI custom prompt', 'prompt_deepseek': 'Old DeepSeek prompt'})
        widget = main.ConfigWidget()
        try:
            with patch.object(main.QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                widget.restore_default_prompt()
            widget.save_settings()
            self.assertEqual(main.prefs['prompt_deepseek'], main.DEFAULT_PROMPT)
            self.assertEqual(main.prefs['prompt_openai'], 'OpenAI custom prompt')
            self.assertEqual(main.prefs['api_key_deepseek'], 'TEST-ONLY-KEY')
        finally:
            widget.close()

    def test_all_provider_requests_are_text_only_even_with_cover_flag(self):
        providers = ['Google Gemini', 'OpenAI', 'DeepSeek', 'Anthropic', 'OpenRouter', 'Local (Ollama/LM Studio)']
        filename = '直到紫藤花开2 [禁漫汉化组] (C108) [坊桥夜泊(坊桥夜泊)] 藤の花が咲くまで2'
        context = {'original_filename': filename, 'parsed_filename': parse_filename(filename).as_dict(),
                   'existing_title': '当前标题', 'send_cover_image': True,
                   'existing_comments': 'PRIVATE COMMENTS DO NOT SEND', 'existing_authors': ['PRIVATE AUTHOR']}
        for provider in providers:
            with self.subTest(provider=provider):
                main.prefs.clear()
                main.prefs['ai_provider'] = provider
                content = json.dumps({'title': '模型错误标题', 'tags': ['错误标签']}, ensure_ascii=False)
                response = {'choices': [{'message': {'content': content}}],
                            'candidates': [{'content': {'parts': [{'text': content}]}}],
                            'content': [{'text': content}]}
                mock_response = unittest.mock.MagicMock()
                mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
                with patch('urllib.request.urlopen', return_value=mock_response) as request:
                    result = main.AIVisionAction.run_api_request(None, 2, 'NO_SUCH_COVER.jpg', '', context)
                self.assertIsInstance(result, tuple, result)
                self.assertEqual(result[1]['title'], '直到紫藤花开 2')
                self.assertFalse(result[1]['cover_image_supplied'])
                payload = json.loads(request.call_args.args[0].data)
                serialized = json.dumps(payload)
                for forbidden in ['image_url', 'inline_data', 'base64', 'google_search', 'tools',
                                  'PRIVATE COMMENTS', 'PRIVATE AUTHOR']:
                    self.assertNotIn(forbidden, serialized)

    def test_review_fields_and_manual_only_defaults(self):
        filename = '直到紫藤花开2 [禁漫汉化组] [坊桥夜泊(坊桥夜泊)] 藤の花が咲くまで2'
        result = normalize_result({}, filename)
        dialog = ui.MetadataReviewDialog(None, result, None)
        try:
            approved = dialog.get_approved_data()
            self.assertEqual(approved['title']['value'], '直到紫藤花开 2')
            self.assertEqual(approved['authors']['value'], '坊桥夜泊')
            self.assertEqual(approved['series_index']['value'], '2')
            self.assertEqual(approved['comments']['value'], filename)
            for key in ('tags', 'publisher', 'pubdate', 'identifiers'):
                self.assertIn(key, approved)
                self.assertTrue(dialog.results[key]['widget'].isEnabled())
                self.assertEqual(dialog.results[key]['widget'].text(), '')
            self.assertNotIn('original_filename', dialog.results)
            self.assertIn('社团：', dialog.filename_details.text())
            if os.environ.get('AI_METADATA_SMOKE_PREVIEW'):
                dialog.resize(1250, 900)
                dialog.show()
                APP.processEvents()
                dialog.grab().save(str(Path(os.environ['AI_METADATA_SMOKE_PREVIEW']) / 'review_complete.png'))
        finally:
            dialog.close()

    def test_manual_review_fields_can_be_selected_edited_and_validated(self):
        result = normalize_result({'tags': ['AI tag'], 'publisher': 'AI publisher', 'ids': 'ai:bad', 'pub_year': 2026}, '标题')
        dialog = ui.MetadataReviewDialog(None, result, None)
        try:
            values = {'tags': '人工标签', 'publisher': '人工出版社', 'pubdate': '2026-10-09', 'identifiers': 'custom:123'}
            for key, value in values.items():
                dialog.results[key]['widget'].setText(value)
            approved = dialog.get_approved_data()
            for key, value in values.items():
                self.assertEqual(approved[key]['value'], value)
                self.assertIs(approved[key]['manual'], True)
            dialog.results['pubdate']['widget'].setText('2026-02-30')
            with patch.object(ui.QMessageBox, 'warning') as warning:
                dialog.accept()
            warning.assert_called_once()
            self.assertEqual(dialog.result(), dialog.DialogCode.Rejected)
            dialog.results['pubdate']['widget'].setText('2026-10-09')
            dialog.accept()
            self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)
        finally:
            dialog.close()

    def test_screenshot_title_recovery_survives_provider_response_and_review(self):
        prefix = '[剥元ここ][禁漫汉化组](C108)[うずらフロンティア(剥元ここ)]'
        japanese = '娘が通勤用オナホになっちゃうまで 前日譚'
        current = prefix + '\\' + japanese + '[中国翻译]'
        context = {'original_filename': prefix, 'existing_title': current,
                   'original_filename_source': 'calibre_path_fallback', 'parsed_filename': parse_filename(prefix).as_dict()}
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        response = {'choices': [{'message': {'content': json.dumps({'title': '模拟中文译名', 'translated_title': '模拟中文译名'})}}]}
        mock_response = unittest.mock.MagicMock()
        mock_response.__enter__.return_value.read.return_value = json.dumps(response).encode()
        with patch('urllib.request.urlopen', return_value=mock_response) as request:
            book_id, metadata, cover, returned_context = main.AIVisionAction.run_api_request(None, 2, None, '', context)
        payload = json.loads(request.call_args.args[0].data)
        prompt = payload['messages'][0]['content'][0]['text']
        self.assertIn('title_evidence_source: existing_title', prompt)
        self.assertIn(japanese, prompt)
        self.assertEqual(metadata['title'], '模拟中文译名')
        self.assertEqual(metadata['original_title'], japanese)
        dialog = ui.MetadataReviewDialog(None, metadata, cover)
        try:
            self.assertEqual(dialog.results['title']['widget'].text(), '模拟中文译名')
            self.assertEqual(dialog.get_approved_data()['title']['value'], '模拟中文译名')
        finally:
            dialog.close()

    def test_fallback_title_and_preserved_input_comments_are_checked(self):
        result = normalize_result({'title': 'invented'}, '[作者][汉化组]', existing_title='人工书名',
                                  filename_source='calibre_path_fallback')
        dialog = ui.MetadataReviewDialog(None, result, None)
        try:
            self.assertEqual(dialog.results['title']['widget'].text(), '人工书名')
            approved = dialog.get_approved_data()
            self.assertEqual(approved['title']['value'], '人工书名')
            self.assertEqual(approved['comments']['value'], '人工书名')
            if os.environ.get('AI_METADATA_SMOKE_PREVIEW'):
                dialog.resize(1250, 900)
                dialog.show()
                APP.processEvents()
                dialog.grab().save(str(Path(os.environ['AI_METADATA_SMOKE_PREVIEW']) / 'review_fallback.png'))
        finally:
            dialog.close()

    def test_library_switch_cancels_remaining_queue(self):
        errors = []
        original_db = SimpleNamespace(library_id='A')
        other_db = SimpleNamespace(library_id='B')
        action = make_action(original_db)
        action.batch_queue = [2, 3]
        action.queue_active = True
        action.gui.current_db.new_api = other_db
        action.signals.error_signal.emit = errors.append
        action.process_next_in_queue()
        self.assertEqual(action.batch_queue, [])
        self.assertFalse(action.queue_active)
        self.assertEqual(len(errors), 1)

    def test_explicit_manual_mode_opens_review(self):
        reviews = []
        action = SimpleNamespace(pending_context={}, review_each=True,
                                 signals=SimpleNamespace(review_signal=SimpleNamespace(emit=lambda *args: reviews.append(args))))
        job = SimpleNamespace(failed=False, result=(2, {'review_required': False}, None, {'library_id': 'A'}))
        main.AIVisionAction.job_finished(action, job)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0][0], 2)

    def test_api_failure_advances_queue_without_writing(self):
        import urllib.error
        main.prefs.clear()
        main.prefs['ai_provider'] = 'DeepSeek'
        with patch('urllib.request.urlopen', side_effect=urllib.error.URLError('test failure')):
            result = main.AIVisionAction.run_api_request(None, 2, None, '', {'original_filename': '标题'})
        self.assertIn('error_msg', result)
        events = []
        action = SimpleNamespace(active_book_id=2, pending_context={}, _record_result=lambda *args: None,
                                 signals=SimpleNamespace(error_signal=SimpleNamespace(emit=lambda x: events.append('error'))),
                                 process_next_in_queue=lambda: events.append('next'),
                                 apply_metadata=lambda *args: self.fail('AI failure must not write metadata'))
        main.AIVisionAction.job_finished(action, SimpleNamespace(failed=False, result=result))
        self.assertEqual(events, ['error', 'next'])

    def test_actual_calibre_database_write_and_source_conflict(self):
        with tempfile.TemporaryDirectory(prefix='ai-metadata-smoke-', dir=ROOT) as directory:
            library = LibraryDatabase(directory)
            library.new_api.create_custom_column('original_filename', 'Original filename', 'text', False)
            library.close()
            library = LibraryDatabase(directory)
            db = library.new_api
            try:
                book_id = db.create_book_entry(Metadata('旧标题', ['旧作者']))
                filename = '直到紫藤花开2 [禁漫汉化组] [坊桥夜泊(坊桥夜泊)] 藤の花が咲くまで2'
                db.set_field('#original_filename', {book_id: filename})
                db.set_field('tags', {book_id: ['人工标签']})
                snap = snapshot_metadata(db, book_id)
                result = normalize_result({}, filename)
                approved = {'title': result['title'], 'authors': result['creators'], 'series': result['series'],
                            'series_index': result['volume'], 'languages': result['languages'],
                            'comments': result['comments'], 'tags': ['不应写入'], '_analysis_record': result}
                written = apply_metadata_safely(db, book_id, approved, snap, db.library_id)
                self.assertEqual(written['status'], 'written')
                mi = db.get_metadata(book_id)
                self.assertEqual(mi.title, result['title'])
                self.assertEqual(mi.title, '直到紫藤花开 2')
                self.assertEqual(mi.series, '直到紫藤花开')
                self.assertEqual(mi.series_index, 2.0)
                self.assertEqual(mi.authors, ['坊桥夜泊'])
                self.assertEqual(mi.tags, ['人工标签'])
                self.assertEqual(mi.languages, ['zho'])
                self.assertEqual(db.field_for('#original_filename', book_id), filename)
                self.assertTrue(db.get_custom_book_data(AUDIT_KEY, (book_id,)))
                snap = snapshot_metadata(db, book_id)
                db.set_field('#original_filename', {book_id: '人工改名.cbz'})
                conflict = apply_metadata_safely(db, book_id, {'title': '不可写入'}, snap, db.library_id)
                self.assertEqual(conflict['status'], 'conflict')
                self.assertEqual(db.get_metadata(book_id).title, result['title'])
                snap = snapshot_metadata(db, book_id)
                manual_values = {'tags': '手动追加标签', 'publisher': '人工出版社',
                                 'pubdate': '2026-10-09', 'identifiers': 'custom:manual-value'}
                dialog = ui.MetadataReviewDialog(None, result, None)
                try:
                    for key, value in manual_values.items():
                        dialog.results[key]['widget'].setText(value)
                    approved = dialog.get_approved_data()
                finally:
                    dialog.close()
                written = apply_metadata_safely(db, book_id, approved, snap, db.library_id)
                self.assertEqual(written['status'], 'written')
                mi = db.get_metadata(book_id)
                self.assertEqual(set(mi.tags), {'人工标签', '手动追加标签'})
                self.assertEqual(mi.publisher, '人工出版社')
                self.assertEqual(mi.pubdate.date().isoformat(), '2026-10-09')
                self.assertEqual(mi.identifiers['custom'], 'manual-value')
            finally:
                library.close()


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CalibreSmokeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
