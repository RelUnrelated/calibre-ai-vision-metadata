import unittest

from result_schema import normalize_result, tag_allowlist_for_library


class ResultSchemaTests(unittest.TestCase):
    def test_recovered_historical_input_repairs_an_already_incorrect_current_title(self):
        original = '僕は谁と付き合えばいいのだろうか'
        filename = '[悠木ヒロ]' + original + '[中国翻译][禁漫去码]'
        result = normalize_result({'title': '模拟中文译名'}, filename, existing_title='禁漫去码',
                                  filename_source='analysis_history', comments_context={
                                      'text': filename, 'source': 'analysis_history', 'write_allowed': True})
        self.assertEqual(result['title'], '模拟中文译名')
        self.assertEqual(result['original_title'], original)
        self.assertEqual(result['comments'], filename)
        self.assertEqual(result['comments_source'], 'analysis_history')
        self.assertTrue(result['warnings'])

    def test_reported_middle_title_remains_translatable_and_comments_keeps_notes(self):
        title = '僕は谁と付き合えばいいのだろうか'
        filename = '[悠木ヒロ]' + title + '[中国翻译][禁漫去码]'
        result = normalize_result({'title': '模拟中文译名', 'series': '禁漫去码', 'volume': '2'}, filename)
        self.assertEqual(result['title'], '模拟中文译名')
        self.assertEqual(result['original_title'], title)
        self.assertEqual(result['creators'], ['悠木ヒロ'])
        self.assertEqual(result['comments'], filename)
        self.assertEqual(result['series'], '')
        self.assertEqual(result['volume'], '')

    def test_ai_cannot_promote_annotations_to_title(self):
        original = '僕は谁と付き合えばいいのだろうか'
        filename = '[悠木ヒロ]' + original + '[中国翻译][禁漫去码]'
        for annotation in ('禁漫去码', '中国翻译', '悠木ヒロ'):
            with self.subTest(annotation=annotation):
                result = normalize_result({'title': annotation, 'translated_title': annotation}, filename)
                self.assertEqual(result['title'], original)
                self.assertEqual(result['translated_title'], '')
                self.assertTrue(result['review_required'])
                self.assertTrue(result['warnings'])

    def test_transliterated_directory_cannot_invent_a_title_missing_from_current_metadata(self):
        result = normalize_result({'title': '模型乱猜'}, '[Zuo Zhe ][Yi Hua Zu ]', existing_title='[作者][汉化组]',
                                  filename_source='calibre_path_fallback')
        self.assertEqual(result['title'], '')
        self.assertEqual(result['creators'], ['作者'])

    def test_current_unicode_metadata_wins_over_transliterated_directory(self):
        result = normalize_result({'title': '中文译名'}, '[Zuo Zhe]Some work',
                                  existing_title='[作者][汉化组]日本語の作品', filename_source='calibre_path_fallback')
        self.assertEqual(result['creators'], ['作者'])
        self.assertEqual(result['translation_group'], '汉化组')
        self.assertEqual(result['languages'], ['zho'])

    def test_standalone_title_cannot_be_copied_to_series(self):
        for source in ('[作者]日本語の作品', '[作者][汉化组]单行本书名', '[作者](C108)日本語の作品 [DL版]'):
            with self.subTest(source=source):
                result = normalize_result({'title': '单行本书名', 'series': '单行本书名', 'volume': '5',
                                           'issue_number': '9'}, source)
                self.assertEqual(result['series'], '')
                self.assertEqual(result['volume'], '')
                self.assertEqual(result['issue_number'], '')

    def test_japanese_title_number_provides_volume_evidence(self):
        result = normalize_result({'title': '中文书名2', 'series': '中文书名', 'volume': '999'}, '[作者]日本語の作品2')
        self.assertEqual(result['title'], '中文书名 2')
        self.assertEqual(result['series'], '中文书名')
        self.assertEqual(result['volume'], '2')

    def test_explicit_volume_marker_is_preserved(self):
        result = normalize_result({'title': '中文书名 第3卷', 'series': '中文书名'}, '[作者]日本語の作品 第3巻')
        self.assertEqual(result['title'], '中文书名 3')
        self.assertEqual(result['series'], '中文书名')
        self.assertEqual(result['volume'], '3')

    def test_volume_title_uses_one_space_and_series_uses_the_same_base(self):
        for source_title in ('直到紫藤花盛开2', '直到紫藤花盛开 2', '直到紫藤花盛开   2',
                             '直到紫藤花盛开第2卷', '直到紫藤花盛开 第 2 卷',
                             '直到紫藤花盛开 卷2', '直到紫藤花盛开 Vol. 2'):
            with self.subTest(source_title=source_title):
                filename = source_title + ' [汉化组]'
                result = normalize_result({'title': '错误书名9', 'series': '错误丛书9'}, filename)
                self.assertEqual(result['title'], '直到紫藤花盛开 2')
                self.assertEqual(result['translated_title'], result['title'])
                self.assertEqual(result['series'], '直到紫藤花盛开')
                self.assertEqual(result['volume'], '2')
                self.assertEqual(result['comments'], filename)
                self.assertEqual(result['original_filename'], filename)

    def test_translated_series_is_derived_from_final_title_instead_of_ai_series(self):
        for translated in ('中文书名', '中文书名2', '中文书名 2', '中文书名9', '中文书名 第9卷', '中文书名 Vol. 9'):
            with self.subTest(translated=translated):
                result = normalize_result({'title': translated, 'series': '另一种译名2', 'volume': '9'},
                                          '[作者]日本語の作品2')
                self.assertEqual(result['title'], '中文书名 2')
                self.assertEqual(result['series'], '中文书名')
                self.assertEqual(result['volume'], '2')
                self.assertEqual(result['original_title'], '日本語の作品2')

    def test_base_title_internal_digits_are_preserved(self):
        result = normalize_result({}, '第7研究所2 [汉化组]')
        self.assertEqual(result['title'], '第7研究所 2')
        self.assertEqual(result['series'], '第7研究所')

    def test_collision_suffix_does_not_create_a_volume_or_series(self):
        result = normalize_result({'series': '单行本书名', 'volume': '2'}, '单行本书名 (2)')
        self.assertEqual(result['title'], '单行本书名')
        self.assertEqual(result['series'], '')
        self.assertEqual(result['volume'], '')

    def test_screenshot_current_filename_title_is_extracted_and_ai_translation_kept(self):
        directory = '[剥元ここ][禁漫汉化组](C108)[うずらフロンティア(剥元ここ)]'
        japanese = '娘が通勤用オナホになっちゃうまで 前日譚'
        current_title = directory + '\\' + japanese + '[中国翻译]'
        result = normalize_result({'title': '模拟中文译名', 'translated_title': '模拟中文译名'},
                                  directory, existing_title=current_title, filename_source='calibre_path_fallback')
        self.assertEqual(result['title'], '模拟中文译名')
        self.assertEqual(result['original_title'], japanese)
        self.assertEqual(result['title_source'], 'ai_translated')
        self.assertTrue(result['title_needs_confirmation'])
        self.assertTrue(result['review_required'])
        self.assertEqual(result['comments'], current_title)
        self.assertEqual(result['comments_source'], 'existing_title_snapshot')
        self.assertEqual(result['creators'], ['剥元ここ'])
        self.assertNotIn('[中国翻译]', result['title'])

    def test_chinese_current_title_after_metadata_groups_wins_over_ai(self):
        current = '[作者][汉化组]直到紫藤花开2[中国翻译]'
        result = normalize_result({'title': '模型乱改', 'translated_title': '模型乱改'}, '[作者][汉化组]',
                                  existing_title=current, filename_source='calibre_path_fallback')
        self.assertEqual(result['title'], '直到紫藤花开 2')
        self.assertEqual(result['series'], '直到紫藤花开')
        self.assertEqual(result['volume'], '2')
        self.assertEqual(result['title_source'], 'existing_title')

    def test_truncated_directory_title_does_not_override_complete_current_title(self):
        result = normalize_result({}, '[作者]完整书', existing_title='[作者]完整书名2[汉化组]',
                                  filename_source='calibre_path_fallback')
        self.assertEqual(result['title'], '完整书名 2')

    def test_echoed_current_filename_is_cleaned(self):
        current = '[作者][汉化组]日本語の作品[中国翻译]'
        result = normalize_result({'title': current}, '[作者][汉化组]', existing_title=current,
                                  filename_source='calibre_path_fallback')
        self.assertEqual(result['title'], '日本語の作品')
        self.assertNotIn('[', result['title'])

    def test_missing_title_cannot_be_invented_from_numeric_suffix(self):
        filename = '[剥元ここ][禁漫汉化组](C108)[うずらフロンティア(剥元ここ)] (2)'
        result = normalize_result({'title': '臆造标题2', 'volume': '2', 'series': '臆造丛书'}, filename)
        self.assertEqual(result['title'], '')
        self.assertEqual(result['volume'], '')
        self.assertEqual(result['series'], '')
        self.assertEqual(result['comments'], filename)
        self.assertTrue(result['title_needs_confirmation'])
        self.assertTrue(result['review_required'])

    def test_missing_title_uses_existing_title_for_manual_confirmation(self):
        result = normalize_result({'title': '臆造标题'}, '[作者][汉化组] (2)', existing_title='人工标题')
        self.assertEqual(result['title'], '人工标题')
        self.assertEqual(result['title_source'], 'existing_title')
        self.assertTrue(result['title_needs_confirmation'])

    def test_path_fallback_always_requires_review(self):
        result = normalize_result({'title': '标题', 'confidence': 1, 'review_required': False}, '标题',
                                  filename_source='calibre_path_fallback')
        self.assertTrue(result['review_required'])
        self.assertTrue(result['warnings'])
        self.assertFalse(result['cover_image_supplied'])
    def test_library_tags_become_allowlist_without_cross_library_state(self):
        class TagDB:
            def all_field_names(self, field):
                self.assert_field = field
                return {"纯爱", "长篇"}

        db = TagDB()
        self.assertEqual(set(tag_allowlist_for_library(db, ["人工授权"])), {"长篇", "纯爱", "人工授权"})
        self.assertEqual(db.assert_field, "tags")

    def test_filename_translation_cannot_be_overwritten(self):
        result = normalize_result(
            {"title": "模型乱翻", "translated_title": "模型乱翻", "creators": [], "tags": "adult, test"},
            "直到紫藤花开3 [禁漫汉化组] (C108) [坊桥夜泊(坊桥夜泊)] 藤の花が咲くまで3 (オリジナル) [中国翻译]",
        )
        self.assertEqual(result["title"], "直到紫藤花开 3")
        self.assertEqual(result["title_source"], "filename")
        self.assertEqual(result["creators"], ["坊桥夜泊"])
        self.assertEqual(result["original_filename"].count("["), 3)
        self.assertEqual(result["comments"], result["original_filename"])
        self.assertEqual(result["series"], "直到紫藤花开")
        self.assertEqual(result["volume"], "3")
        self.assertEqual(result["issue_number"], "")
        self.assertEqual(result["languages"], ["zho"])
        self.assertEqual(result["publisher"], "")
        self.assertIsNone(result["pub_year"])
        self.assertFalse(result["title_only"])

    def test_ai_summary_never_replaces_filename_comments(self):
        filename = r"[禁漫汉化组]\(C108)[French letter(藤崎ひかり)]作品 [DL版]"
        result = normalize_result(
            {"title": "作品", "comments": "Invented AI synopsis"},
            filename,
        )
        self.assertEqual(result["comments"], filename)

    def test_directory_without_a_title_snapshot_is_never_written_to_comments(self):
        result = normalize_result({'title': '模型猜测', 'comments': 'AI摘要'}, '截断目录 (2)',
                                  filename_source='calibre_path_fallback')
        self.assertEqual(result['comments'], '')
        self.assertFalse(result['comments_write_allowed'])

    def test_invalid_result_type_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_result(["not", "an", "object"], "x.cbz")

    def test_empty_tag_allowlist_disables_ai_tags(self):
        result = normalize_result({"title": "标题", "tags": ["模型自造标签"]}, "x.cbz", allowed_tags=set())
        self.assertEqual(result["tags"], [])

    def test_tags_are_disabled_even_when_authorized(self):
        result = normalize_result(
            {"title": "标题", "tags": ["恋爱", "模型自造标签"]},
            "标题.cbz",
            allowed_tags={"恋爱", "纯爱"},
        )
        self.assertEqual(result["tags"], [])


if __name__ == "__main__":
    unittest.main()
