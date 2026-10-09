import unittest

from filename_parser import parse_filename, read_filename_source


class FilenameParserTests(unittest.TestCase):
    def test_middle_title_wins_over_trailing_bracket_annotations(self):
        title = '僕は谁と付き合えばいいのだろうか'
        for notes in ('[中国翻译][禁漫去码]', '[中国翻译][全彩]', '[附录2][修订版]'):
            with self.subTest(notes=notes):
                filename = '[悠木ヒロ]' + title + notes
                result = parse_filename(filename)
                self.assertEqual(result.original_title, title)
                self.assertEqual(result.translated_title, '')
                self.assertEqual(result.creators, ['悠木ヒロ'])
                self.assertEqual(result.series, '')
                self.assertEqual(result.volume, '')
                self.assertEqual(result.original_filename, filename)

    def test_middle_chinese_title_wins_over_trailing_notes(self):
        result = parse_filename('[作者]正确中文书名2[全彩][禁漫去码]')
        self.assertEqual(result.translated_title, '正确中文书名2')
        self.assertEqual(result.original_title, '')
        self.assertEqual(result.series, '正确中文书名')
        self.assertEqual(result.volume, '2')

    def test_bracketed_title_keeps_author_and_circle(self):
        result = parse_filename('[みちきんぐ][淫魔学生会色色执行部3][あんみつよもぎ亭 (みちきんぐ)] (396)')
        self.assertEqual(result.translated_title, '淫魔学生会色色执行部3')
        self.assertEqual(result.creators, ['みちきんぐ'])
        self.assertEqual(result.circle, 'あんみつよもぎ亭')
        self.assertEqual(result.series, '淫魔学生会色色执行部')
        self.assertEqual(result.volume, '3')
        self.assertTrue(result.review_required)

    def test_metadata_only_filename_has_no_title_or_volume(self):
        filename = '[剥元ここ][禁漫汉化组](C108)[うずらフロンティア(剥元ここ)] (2)'
        result = parse_filename(filename)
        self.assertEqual(result.original_filename, filename)
        self.assertEqual(result.translated_title, '')
        self.assertEqual(result.original_title, '')
        self.assertEqual(result.volume, '')
        self.assertNotEqual(result.source_publication, '2')

    def test_calibre_directory_id_is_not_source_filename_suffix(self):
        class DB:
            field_metadata = {'#original_filename': {}}
            original = ''
            def field_for(self, field, book_id, default=''):
                return self.original if field == '#original_filename' else '作者/作品2 (2)'
        db = DB()
        result = read_filename_source(db, 2)
        self.assertEqual(result['original_filename'], '作品2')
        self.assertEqual(result['original_filename_source'], 'calibre_path_fallback')
        db.original = ' 完整文件名 (2).cbz '
        result = read_filename_source(db, 2)
        self.assertEqual(result['original_filename'], db.original)
        self.assertEqual(result['original_filename_source'], 'custom_column')
        db.field_metadata = {}
        self.assertEqual(read_filename_source(db, 2)['original_filename'], '作品2')
    def test_standard_translation_group(self):
        result = parse_filename("[白杨汉化组] [テツナ] 好きな子はいじめたくなるモノ (COMIC 阿吽 改 Vol.18) [中国翻译]")
        self.assertEqual(result.creators, ["テツナ"])
        self.assertEqual(result.translation_group, "白杨汉化组")
        self.assertEqual(result.original_title, "好きな子はいじめたくなるモノ")
        self.assertNotIn("白杨汉化组", result.original_title)

    def test_circle_and_author(self):
        result = parse_filename(r"[禁漫汉化组]\(C108)[French letter(藤崎ひかり)]はじめまして!わたし、中坚同人作家です [DL版]")
        self.assertEqual(result.creators, ["藤崎ひかり"])
        self.assertEqual(result.circle, "French letter")
        self.assertEqual(result.event_code, "C108")
        self.assertEqual(result.edition, "DL版")
        self.assertIn("はじめまして", result.original_title)
        self.assertFalse(result.original_title.startswith("\\"))
        self.assertIn(r"\(C108)", result.original_filename)

    def test_existing_chinese_title_wins(self):
        result = parse_filename("直到紫藤花开3 [禁漫汉化组] (C108) [坊桥夜泊(坊桥夜泊)] 藤の花が咲くまで3 (オリジナル) [中国翻译]")
        self.assertEqual(result.translated_title, "直到紫藤花开3")
        self.assertEqual(result.title_source, "filename")
        self.assertEqual(result.creators, ["坊桥夜泊"])
        self.assertEqual(result.original_filename, "直到紫藤花开3 [禁漫汉化组] (C108) [坊桥夜泊(坊桥夜泊)] 藤の花が咲くまで3 (オリジナル) [中国翻译]")


if __name__ == "__main__":
    unittest.main()
