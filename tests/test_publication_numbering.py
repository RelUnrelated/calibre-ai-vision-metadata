import unittest

from filename_parser import parse_filename
from metadata_writer import prepare_automatic_update
from result_schema import normalize_result


class PublicationNumberingTests(unittest.TestCase):
    def test_magazine_volume_never_becomes_work_title_number(self):
        original = '好きな子はいじめたくなるモノ'
        filename = '[白杨汉化组][テツナ]' + original + ' (COMIC 阿吽 改 Vol.18) [中国翻译]'
        for translated in ('喜欢的孩子让人想要欺负 18', '喜欢的孩子让人想要欺负18',
                           '喜欢的孩子让人想要欺负 Vol.18', '喜欢的孩子让人想要欺负 第18卷'):
            with self.subTest(translated=translated):
                result = normalize_result({'title': translated, 'translated_title': translated}, filename)
                self.assertEqual(result['title'], '喜欢的孩子让人想要欺负')
                self.assertEqual(result['translated_title'], result['title'])
                self.assertEqual(result['volume'], '')
                self.assertEqual(result['series'], '')
                self.assertEqual(result['provider_title'], translated)
                self.assertEqual(result['comments'], filename)
                self.assertEqual(result['source_publication'], 'COMIC 阿吽 改 Vol.18')
                self.assertNotIn('series_index', prepare_automatic_update(result))

    def test_accepted_ai_roles_do_not_bypass_numbering_guard(self):
        original = '好きな子はいじめたくなるモノ'
        filename = '[テツナ]' + original + '(COMIC 阿吽 改 Vol.18)'
        result = normalize_result({'title': '喜欢的孩子让人想要欺负 18', 'filename_roles': {
            'title_text': original, 'title_language': 'ja', 'title_confidence': 0.95,
            'author_texts': ['テツナ'], 'circle_text': '', 'annotation_texts': [],
            'confidence': 0.9, 'uncertain': False,
        }}, filename)
        self.assertEqual(result['filename_role_status'], 'accepted')
        self.assertEqual(result['title'], '喜欢的孩子让人想要欺负')

    def test_current_title_fallback_gets_same_guard(self):
        current = '[作者]日本語の作品(COMIC magazine Vol.18)'
        result = normalize_result({'title': '中文译名 18'}, 'Truncated directory',
                                  existing_title=current, filename_source='calibre_path_fallback')
        self.assertEqual(result['title'], '中文译名')
        self.assertEqual(result['comments'], current)

    def test_actual_work_volume_wins_over_magazine_number(self):
        source = '[作者]日本語の作品2(COMIC magazine Vol.18)'
        result = normalize_result({'title': '中文译名 18'}, source)
        self.assertEqual(result['title'], '中文译名 2')
        self.assertEqual(result['volume'], '2')
        self.assertEqual(result['series'], '中文译名')

    def test_internal_title_numbers_are_preserved(self):
        result = normalize_result({'title': '第7研究所的秘密 18'}, '[作者]第7研究所の秘密(COMIC Vol.18)')
        self.assertEqual(result['title'], '第7研究所的秘密')
        result = normalize_result({'title': '编号7'}, '[作者]7号の秘密(COMIC Vol.18)')
        self.assertEqual(result['title'], '编号7')

    def test_written_source_numbers_may_be_translated_into_digits(self):
        result = normalize_result({'title': '秘密编号18'}, '[作者]秘密番号十八の謎')
        self.assertEqual(result['title'], '秘密编号18')

    def test_publication_number_inside_title_text_is_not_deleted_blindly(self):
        result = normalize_result({'title': '18岁的秘密'}, '[作者]日本語の作品(COMIC Vol.18)')
        self.assertEqual(result['title'], '18岁的秘密')
        # This guard targets appended numbering, not translation semantics.

    def test_decimal_and_range_suffixes_need_source_evidence(self):
        for number in ('18.5', '18-20'):
            result = normalize_result({'title': '中文译名 ' + number}, '[作者]日本語の作品(COMIC Vol.18)')
            self.assertEqual(result['title'], '中文译名')


if __name__ == '__main__':
    unittest.main()
