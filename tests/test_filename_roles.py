import unittest

from filename_parser import parse_filename
from metadata_writer import prepare_automatic_update
from result_schema import normalize_result


def roles(title, authors=(), *, circle='', notes=(), confidence=0.95, uncertain=False):
    return {'title_text': title, 'author_texts': list(authors), 'circle_text': circle,
            'annotation_texts': list(notes), 'confidence': confidence, 'uncertain': uncertain}


class FilenameRoleTests(unittest.TestCase):
    def test_ai_corrects_reversed_bracket_title_and_author(self):
        title = '僕は誰と付き合えばいいのだろうか'
        filename = '[' + title + '][悠木ヒロ][中国翻译]'
        parsed = parse_filename(filename)
        self.assertEqual(parsed.creators, [title])  # A fallible first-bracket guess.
        result = normalize_result({'title': '模拟中文译名',
                                  'filename_roles': roles(title, ['悠木ヒロ'], notes=['中国翻译'])}, filename, parsed)
        self.assertEqual(result['creators'], ['悠木ヒロ'])
        self.assertEqual(result['original_title'], title)
        self.assertEqual(result['title'], '模拟中文译名')
        self.assertEqual(result['filename_role_status'], 'accepted')
        self.assertEqual(result['comments'], filename)
        self.assertEqual(parsed.creators, [title])
        self.assertTrue(any(item.startswith('ai-role-title:') for item in result['evidence']))

    def test_ai_recovers_bracketed_chinese_title_without_retranslating(self):
        filename = '[正确中文书名2][悠木ヒロ][全彩]'
        result = normalize_result({'title': '模型另译名9', 'volume': '9',
                                  'filename_roles': roles('正确中文书名2', ['悠木ヒロ'], notes=['全彩'])}, filename)
        self.assertEqual(result['title'], '正确中文书名 2')
        self.assertEqual(result['series'], '正确中文书名')
        self.assertEqual(result['volume'], '2')
        self.assertEqual(result['creators'], ['悠木ヒロ'])

    def test_ai_separates_unbracketed_author_from_japanese_title(self):
        title = '僕は誰と付き合えばいいのだろうか'
        filename = '悠木ヒロ - ' + title + ' [中国翻译]'
        result = normalize_result({'title': '模拟中文译名',
                                  'filename_roles': roles(title, ['悠木ヒロ'], notes=['中国翻译'])}, filename)
        self.assertEqual(result['original_title'], title)
        self.assertEqual(result['creators'], ['悠木ヒロ'])
        self.assertEqual(result['title'], '模拟中文译名')

    def test_ai_removes_author_label_while_preserving_chinese_title_wording(self):
        filename = '作者张三 - 正确中文书名2 [全彩]'
        result = normalize_result({'title': 'AI乱翻',
                                  'filename_roles': roles('正确中文书名2', ['张三'], notes=['全彩'])}, filename)
        self.assertEqual(result['title'], '正确中文书名 2')
        self.assertEqual(result['creators'], ['张三'])
        self.assertEqual(result['comments'], filename)

    def test_explicit_chinese_title_cannot_be_replaced_by_other_source_text(self):
        filename = '正确中文书名 [作者][另一个词]'
        result = normalize_result({'title': '另一个词',
                                  'filename_roles': roles('另一个词', ['作者'])}, filename)
        self.assertEqual(result['filename_role_status'], 'invalid')
        self.assertEqual(result['title'], '正确中文书名')
        self.assertEqual(prepare_automatic_update(result), {})

    def test_missing_author_remains_empty_instead_of_using_an_ai_guess(self):
        filename = '日本語の作品[中国翻译]'
        result = normalize_result({'title': '模拟中文译名', 'creators': ['模型臆造'],
                                  'filename_roles': roles('日本語の作品', notes=['中国翻译'])}, filename)
        self.assertEqual(result['creators'], [])
        self.assertNotIn('authors', prepare_automatic_update(result))

    def test_roles_must_quote_the_selected_input(self):
        filename = '[作者]日本語の作品[中国翻译][禁漫去码]'
        for proposed in (roles('不存在的标题', ['作者']), roles('日本語の作品', ['臆造作者']),
                         roles('日本語の作品', ['作者'], circle='臆造社团'),
                         roles('日本語の作品', ['作者'], notes=['不存在的注释'])):
            with self.subTest(proposed=proposed):
                result = normalize_result({'title': '模拟中文译名', 'filename_roles': proposed}, filename)
                self.assertEqual(result['filename_role_status'], 'invalid')
                self.assertEqual(prepare_automatic_update(result), {})

    def test_annotations_cannot_be_titles_or_authors(self):
        filename = '[作者]日本語の作品[中国翻译][禁漫去码][全彩](C108)'
        for proposed in (roles('中国翻译', ['作者']), roles('禁漫去码', ['作者']), roles('全彩', ['作者']),
                         roles('C108', ['作者']), roles('日本語の作品', ['禁漫去码'])):
            with self.subTest(proposed=proposed):
                result = normalize_result({'filename_roles': proposed}, filename)
                self.assertEqual(result['filename_role_status'], 'invalid')

    def test_numeric_collision_suffix_is_not_a_title(self):
        result = normalize_result({'filename_roles': roles('2', ['作者'])}, '[作者][汉化组] (2)')
        self.assertEqual(result['filename_role_status'], 'invalid')
        self.assertEqual(prepare_automatic_update(result), {})

    def test_uncertain_roles_skip_automatic_write(self):
        for confidence, uncertain in ((0.6, False), (0.95, True)):
            with self.subTest(confidence=confidence, uncertain=uncertain):
                result = normalize_result({'title': '模拟中文译名', 'filename_roles': roles(
                    '日本語の作品', ['作者'], confidence=confidence, uncertain=uncertain)}, '[作者]日本語の作品')
                self.assertEqual(result['filename_role_status'], 'uncertain')
                self.assertTrue(result['review_required'])
                self.assertEqual(prepare_automatic_update(result), {})

    def test_malformed_roles_cannot_silently_enable_automatic_writing(self):
        malformed = [None, [], {}, roles('日本語の作品', ['作者'], confidence=float('nan')),
                     roles('日本語の作品', ['作者'], confidence=2),
                     dict(roles('日本語の作品', ['作者']), author_texts='作者'),
                     dict(roles('日本語の作品', ['作者']), uncertain='false')]
        for proposed in malformed:
            with self.subTest(proposed=proposed):
                result = normalize_result({'title': '模拟中文译名', 'filename_roles': proposed}, '[作者]日本語の作品')
                self.assertEqual(result['filename_role_status'], 'invalid')
                self.assertEqual(prepare_automatic_update(result), {})

    def test_roles_respect_explicit_circle_author_evidence(self):
        filename = '[社团(作者)]日本語の作品'
        for proposed in (roles('日本語の作品', ['社团']), roles('日本語の作品', [], circle='作者')):
            with self.subTest(proposed=proposed):
                result = normalize_result({'filename_roles': proposed}, filename)
                self.assertEqual(result['filename_role_status'], 'invalid')
        result = normalize_result({'title': '模拟中文译名', 'filename_roles': roles(
            '日本語の作品', ['作者'], circle='社团')}, filename)
        self.assertEqual(result['filename_role_status'], 'accepted')
        self.assertEqual(result['circle'], '社团')

    def test_title_cannot_include_the_only_author_occurrence(self):
        title = '悠木ヒロ - 日本語の作品'
        result = normalize_result({'filename_roles': roles(title, ['悠木ヒロ'])}, title)
        self.assertEqual(result['filename_role_status'], 'invalid')

    def test_original_japanese_evidence_remains_when_chinese_title_also_exists(self):
        filename = '正确中文书名2 [社团(作者)] 日本語の作品2'
        result = normalize_result({'filename_roles': roles('正确中文书名2', ['作者'], circle='社团')}, filename)
        self.assertEqual(result['title'], '正确中文书名 2')
        self.assertEqual(result['original_title'], '日本語の作品2')

    def test_current_unicode_input_is_used_for_directory_fallback_roles(self):
        current = '[作者]日本語の作品[中国翻译]'
        result = normalize_result({'title': '模拟中文译名', 'filename_roles': roles(
            '日本語の作品', ['作者'], notes=['中国翻译'])}, '[Zuo Zhe]Truncated',
            existing_title=current, filename_source='calibre_path_fallback')
        self.assertEqual(result['filename_role_status'], 'accepted')
        self.assertEqual(result['creators'], ['作者'])
        self.assertEqual(result['comments'], current)


if __name__ == '__main__':
    unittest.main()
