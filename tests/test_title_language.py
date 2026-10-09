import unittest

from filename_parser import parse_filename
from metadata_writer import prepare_automatic_update
from result_schema import normalize_result


def classified(title, language, **extra):
    return dict(title_text=title, author_texts=['作者'], circle_text='',
                annotation_texts=[], confidence=0.95, uncertain=False,
                title_language=language, **extra)


class TitleLanguageTests(unittest.TestCase):
    def test_reported_mixed_titles_are_japanese(self):
        for title in ('乳首感度調查、はじめます', '高飞车巨乳お嬢样と秘密のえっち'):
            with self.subTest(title=title):
                self.assertEqual(parse_filename(title).title_language_hint, 'ja')

    def test_korean_and_english_titles_are_translatable(self):
        cases = [('웹툰 제목', '韩文标题', 'ko'), ('Blue Archive', '蔚蓝档案', 'en')]
        for source_title, translated, language in cases:
            with self.subTest(source_title=source_title):
                self.assertEqual(parse_filename(source_title).title_language_hint, language)
                result = normalize_result({'title': translated, 'filename_roles': classified(source_title, language)},
                                          '[作者]' + source_title)
                self.assertEqual(result['title'], translated)
                self.assertEqual(result['translation_status'], 'translated')

    def test_han_korean_mixed_title_is_not_treated_as_chinese(self):
        source_title = '迷宫干던전 속 사정'
        self.assertEqual(parse_filename(source_title).title_language_hint, 'ko')
        result = normalize_result(
            {'title': '迷宫干地下城里的情况',
             'filename_roles': classified(source_title, 'ko')},
            '[作者]' + source_title)
        self.assertEqual(result['title'], '迷宫干地下城里的情况')
        self.assertEqual(result['translation_status'], 'translated')

    def test_chinese_prefix_and_japanese_suffix_are_not_truncated(self):
        source = '在被作为种马(救世主)所召唤的异世界被精灵妈妈宠爱着一个劲地幹个不停[Amerins汉化] [一亿万轩茶屋 (旅口工路)] 种马（救世主）として召唤された异世界でエル'
        parsed = parse_filename(source)
        self.assertIn('一个劲地幹个不停', parsed.original_title)
        self.assertNotEqual(parsed.original_title, '在被作为种马')

    def test_source_echo_in_translation_field_does_not_hide_chinese_title(self):
        for original, translation in (
            ('乳首感度調查、はじめます', '乳头敏感度调查，开始了'),
            ('高飞车巨乳お嬢样と秘密のえっち', '与傲慢的巨乳大小姐的秘密性爱'),
        ):
            with self.subTest(original=original):
                result = normalize_result({'title': translation, 'translated_title': original}, original)
                self.assertEqual(result['title'], translation)
                self.assertEqual(result['translation_status'], 'translated')

    def test_source_echo_is_not_successful_translation(self):
        original = '乳首感度調查、はじめます'
        result = normalize_result({'title': original, 'translated_title': original}, original)
        self.assertEqual(result['translation_status'], 'needs_translation')
        self.assertEqual(result['translated_title'], '')
        self.assertEqual(prepare_automatic_update(result), {})

    def test_all_kanji_is_provisional_instead_of_confirmed_chinese(self):
        self.assertEqual(parse_filename('[作者]放課後').title_language_hint, 'han_ambiguous')

    def test_all_kanji_japanese_translation_is_not_overwritten(self):
        for title, translation in [('放課後', '放学后'), ('図書委員', '图书委员'), ('秘密', '秘密')]:
            with self.subTest(title=title):
                source = '[作者]' + title + '[中国翻译]'
                result = normalize_result({'title': translation, 'translated_title': translation,
                                           'filename_roles': classified(title, 'ja')}, source)
                self.assertEqual(result['filename_role_status'], 'accepted')
                self.assertEqual(result['title'], translation)
                self.assertEqual(result['original_title'], title)
                self.assertEqual(result['title_source'], 'ai_translated')
                self.assertEqual(result['comments'], source)

    def test_chinese_language_preserves_existing_wording(self):
        result = normalize_result({'title': '模型乱改', 'filename_roles': classified('放学后2', 'zh')},
                                  '[作者]放学后2')
        self.assertEqual(result['title'], '放学后 2')
        self.assertEqual(result['series'], '放学后')

    def test_all_kanji_translation_keeps_volume_and_chapter(self):
        result = normalize_result({'title': '放学后', 'filename_roles': classified('放課後2', 'ja')},
                                  '[作者]放課後2[Ch.15]')
        self.assertEqual(result['title'], '放学后 2 第15话')
        self.assertEqual(result['series'], '放学后')
        self.assertEqual(result['volume'], '2')

    def test_unknown_language_does_not_automatically_rewrite(self):
        result = normalize_result({'title': '模型猜测', 'filename_roles': classified('秘密', 'unknown')}, '[作者]秘密')
        self.assertEqual(result['filename_role_status'], 'uncertain')
        self.assertEqual(prepare_automatic_update(result), {})

    def test_language_cannot_bypass_literal_quote_validation(self):
        result = normalize_result({'title': '放学后', 'filename_roles': classified('不存在', 'ja')}, '[作者]放課後')
        self.assertEqual(result['filename_role_status'], 'invalid')

    def test_separate_chinese_title_has_precedence(self):
        source = '放学后 [作者] 放課後の秘密 [中国翻译]'
        self.assertEqual(parse_filename(source).title_language_hint, 'zh')
        result = normalize_result({'title': '模型乱改', 'filename_roles': classified('放学后', 'ja')}, source)
        self.assertEqual(result['filename_role_status'], 'invalid')
        self.assertEqual(result['title'], '放学后')

    def test_halfwidth_kana_is_japanese(self):
        parsed = parse_filename('[作者]秘密ﾉ部屋')
        self.assertEqual(parsed.translated_title, '')
        self.assertEqual(parsed.title_language_hint, 'ja')

    def test_invalid_language_is_rejected(self):
        for language in ([], {}, True, 'Japanese'):
            with self.subTest(language=language):
                result = normalize_result({'filename_roles': classified('放課後', language)}, '[作者]放課後')
                self.assertEqual(result['filename_role_status'], 'invalid')

    def test_low_confidence_language_cannot_enable_writes(self):
        roles = classified('放課後', 'ja')
        roles['confidence'] = 0.5
        result = normalize_result({'title': '放学后', 'filename_roles': roles}, '[作者]放課後')
        self.assertEqual(result['filename_role_status'], 'uncertain')
        self.assertEqual(prepare_automatic_update(result), {})

    def test_legacy_results_preserve_wording_without_language_evidence(self):
        self.assertEqual(normalize_result({'title': '乱改'}, '[作者]中文书名')['title'], '中文书名')

    def test_current_title_fallback_uses_same_language_analysis(self):
        result = normalize_result({'title': '放学后', 'filename_roles': classified('放課後', 'ja')},
                                  '[作者]', existing_title='[作者]放課後', filename_source='calibre_path_fallback')
        self.assertEqual(result['title'], '放学后')
        self.assertEqual(result['original_title'], '放課後')
