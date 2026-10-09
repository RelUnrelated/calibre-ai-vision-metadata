import unittest

from filename_parser import parse_filename
from result_schema import normalize_result
from metadata_writer import prepare_automatic_update


class KavitaNumberingTests(unittest.TestCase):
    def test_explicit_volume_conventions(self):
        for marker, number in [('v02', '2'), ('Volume 02', '2'), ('vol_002', '2'),
                               ('Vol. 7.5', '7.5'), ('t02', '2'), ('tome 2', '2'),
                               ('第02册', '2'), ('冊2', '2'), ('2巻', '2')]:
            with self.subTest(marker=marker):
                source = '[作者]作品 ' + marker
                parsed = parse_filename(source)
                self.assertEqual(parsed.volume, number)
                self.assertEqual(parsed.series, '作品')
                result = normalize_result({}, source)
                self.assertEqual(result['title'], '作品 ' + number)
                self.assertEqual(result['series'], '作品')
                update = prepare_automatic_update(result)
                self.assertEqual(float(update['series_index']['value']), float(number))

    def test_ranges_are_not_single_series_indices(self):
        for marker in ('v01-v05', 'Vol. 1-5', '第1-5卷'):
            with self.subTest(marker=marker):
                result = normalize_result({'volume': '1'}, '[作者]作品 ' + marker)
                self.assertEqual(result['volume_range'], '1-5')
                self.assertEqual(result['volume'], '')
                self.assertEqual(result['series'], '')
                self.assertIn('1-5', result['title'])
                self.assertNotIn('series_index', prepare_automatic_update(result))

    def test_chapter_does_not_become_volume(self):
        for marker, number in [('ch015', '15'), ('Chapter 15.5', '15.5'),
                               ('ch001-ch006', '1-6'), ('第15话', '15'), ('15話', '15')]:
            with self.subTest(marker=marker):
                result = normalize_result({}, '[作者]作品 ' + marker)
                self.assertEqual(result['chapter'] or result['chapter_range'], number)
                self.assertEqual(result['volume'], '')
                self.assertEqual(result['issue_number'], '')
                self.assertEqual(result['title'], f'作品 第{number}话')
                self.assertNotIn('series_index', prepare_automatic_update(result))

    def test_mixed_numbering_and_duplicate_volume(self):
        result = normalize_result({}, '[作者]作品_v02_ch015_-_vol06_omake')
        self.assertEqual(result['volume'], '2')
        self.assertEqual(result['chapter'], '15')
        self.assertEqual(result['title'], '作品 2 第15话')
        self.assertEqual(result['series'], '作品')
        self.assertEqual(prepare_automatic_update(result)['series_index']['value'], '2')

    def test_local_conflicts_keep_precedence(self):
        source = '(C108)[社团(作者)]作品2[中国翻译][DL版]'
        result = normalize_result({}, source)
        self.assertEqual(result['event_code'], 'C108')
        self.assertEqual(result['chapter'], '')
        self.assertEqual(result['creators'], ['作者'])
        self.assertEqual(result['circle'], '社团')
        self.assertEqual(result['title'], '作品 2')
        self.assertEqual(result['comments'], source)
        parsed = parse_filename('[作者]作品2 ch15')
        self.assertEqual(parsed.volume, '2')
        self.assertEqual(parsed.chapter, '15')

    def test_separate_numbering_groups_and_publication(self):
        for title in ('作品', '[作品]', '日本語の作品'):
            with self.subTest(title=title):
                parsed = parse_filename('[作者]' + title + '[Vol. 02](Ch.15)[中国翻译]')
                self.assertEqual(parsed.creators, ['作者'])
                self.assertEqual(parsed.volume, '2')
                self.assertEqual(parsed.chapter, '15')
                self.assertEqual(parsed.series, title.strip('[]'))
        result = parse_filename('[作者]作品(COMIC magazine Vol.18)')
        self.assertEqual(result.volume, '')
        self.assertEqual(result.source_publication, 'COMIC magazine Vol.18')

    def test_numbering_groups_without_a_title_cannot_create_a_title(self):
        result = normalize_result({'title': '猜测'}, '[作者][Vol. 2][Ch.15]')
        self.assertEqual(result['title'], '')
        self.assertEqual(result['volume'], '')

    def test_ai_quotes_can_omit_numbering_groups(self):
        result = normalize_result({'title': '错误改名', 'filename_roles': {
            'title_text': '作品', 'author_texts': ['作者'], 'circle_text': '',
            'annotation_texts': ['Vol. 2', 'Ch.15'], 'confidence': 0.95, 'uncertain': False,
        }}, '[作者]作品[Vol. 2][Ch.15]')
        self.assertEqual(result['filename_role_status'], 'accepted')
        self.assertEqual(result['title'], '作品 2 第15话')
        self.assertEqual(result['volume'], '2')
        self.assertEqual(result['chapter'], '15')

    def test_translation_uses_source_numbers_and_same_series_base(self):
        result = normalize_result({'title': '中文译名 Vol. 999 ch999'},
                                  '[作者]日本語の作品 v02 ch015')
        self.assertEqual(result['title'], '中文译名 2 第15话')
        self.assertEqual(result['series'], '中文译名')

    def test_ai_quote_with_volume_keeps_separate_chapter(self):
        result = normalize_result({'filename_roles': {
            'title_text': '作品2', 'author_texts': ['作者'], 'circle_text': '',
            'annotation_texts': ['Ch.15'], 'confidence': 0.95, 'uncertain': False,
        }}, '[作者]作品2[Ch.15]')
        self.assertEqual(result['title'], '作品 2 第15话')

    def test_decimal_title_and_collision_suffix(self):
        result = normalize_result({}, '[作者]作品7.5 (2)')
        self.assertEqual(result['title'], '作品 7.5')
        self.assertEqual(result['volume'], '7.5')

    def test_events_next_to_unicode_or_underscore_are_not_chapters(self):
        for source in ('作品_C108_ch15', '作品 C108日本語', '(c108)[社团(作者)]作品2'):
            with self.subTest(source=source):
                result = parse_filename(source)
                self.assertEqual(result.event_code, 'C108')
                self.assertNotEqual(result.chapter, '108')


if __name__ == '__main__':
    unittest.main()
