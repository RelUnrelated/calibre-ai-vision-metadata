import unittest

from result_schema import normalize_result
from metadata_writer import prepare_automatic_update


class TitleOnlyTests(unittest.TestCase):
    def result(self, **changes):
        roles = dict(title_text='お嬢样、调教される快乐に溺れる', title_language='ja',
                     author_texts=[], circle_text='', annotation_texts=[], confidence=0.6,
                     uncertain=False, title_confidence=0.95)
        roles.update(changes)
        return normalize_result({'title': '大小姐，沉溺于被调教的快乐', 'filename_roles': roles},
                                'お嬢样、调教される快乐に溺れる')

    def test_reliable_title_does_not_depend_on_unknown_authors(self):
        result = self.result()
        self.assertEqual(result['filename_role_status'], 'title_only')
        self.assertTrue(result['title_only'])
        update = prepare_automatic_update(result)
        self.assertEqual(update['title']['value'], '大小姐，沉溺于被调教的快乐')
        self.assertEqual(set(update), {'title', 'comments', '_analysis_record'})

    def test_low_or_absent_title_confidence_does_not_bypass_role_checks(self):
        for value in (None, 0.5):
            result = self.result(title_confidence=value)
            self.assertEqual(result['filename_role_status'], 'uncertain')
            self.assertEqual(prepare_automatic_update(result), {})

    def test_invalid_title_confidence_is_rejected(self):
        for value in (True, '0.95', -1, 2, float('nan'), float('inf')):
            result = self.result(title_confidence=value)
            self.assertEqual(result['filename_role_status'], 'invalid')

    def test_title_only_cannot_use_an_invented_title_or_author(self):
        for changes in ({'title_text': '不存在的标题'}, {'author_texts': ['不存在的作者']}):
            result = self.result(**changes)
            self.assertEqual(result['filename_role_status'], 'invalid')

    def test_title_only_requires_exact_deterministic_title(self):
        result = self.result(title_text='お嬢样')
        self.assertEqual(result['filename_role_status'], 'uncertain')

    def test_uncertain_language_cannot_be_promoted_to_title_only(self):
        roles = dict(title_text='秘密', title_language='unknown', author_texts=[], circle_text='',
                     annotation_texts=[], confidence=0.6, uncertain=False, title_confidence=0.95)
        result = normalize_result({'title': '猜测', 'filename_roles': roles}, '秘密')
        self.assertEqual(result['filename_role_status'], 'uncertain')
        self.assertEqual(prepare_automatic_update(result), {})
