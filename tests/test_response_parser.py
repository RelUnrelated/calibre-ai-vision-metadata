import json
import unittest

from result_schema import extract_metadata_json


class ResponseParserTests(unittest.TestCase):
    def test_format_marker_before_metadata_matches_reported_error(self):
        metadata = {'series': '像天敌般的小丫头变成通勤用飞机杯为止 前日谭', 'volume': '',
                    'issue_number': '', 'title': '像天敌般的小丫头变成通勤用飞机杯为止 前日谭',
                    'creators': ['剥元ここ']}
        raw = '{"type": "json_object"}\n' + json.dumps(metadata, ensure_ascii=False)
        self.assertEqual(extract_metadata_json(raw), metadata)

    def test_markdown_and_separate_code_blocks(self):
        raw = 'Format:\n```json\n{"type":"json_object"}\n```\nResult:\n```json\n{"title":"中文书名"}\n```'
        self.assertEqual(extract_metadata_json(raw), {'title': '中文书名'})

    def test_nested_evidence_braces_and_escaped_quotes_are_preserved(self):
        metadata = {'title': '书名 {特别篇}', 'evidence': [{'text': 'A "quoted" value {test}'}],
                    'comments': 'path\\filename.cbz'}
        self.assertEqual(extract_metadata_json(json.dumps(metadata)), metadata)

    def test_schema_preamble_and_trailing_format_marker_are_ignored(self):
        raw = '{"type":"object","properties":{"title":{"type":"string"}}}'
        raw += '{"title":"实际书名"}{"type":"json_object"}'
        self.assertEqual(extract_metadata_json(raw)['title'], '实际书名')

    def test_format_marker_alone_and_unrelated_objects_are_rejected(self):
        for raw in ('{"type":"json_object"}', '{"confidence": 1}', '{}', 'No JSON',
                    '{"properties":{"title":"schema field"}}', '[{"title":"array item"}]'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                extract_metadata_json(raw)

    def test_truncated_or_malformed_json_is_not_repaired_from_nested_object(self):
        for raw in ('{"title":"truncated', '{"type":"json_object"}\n{"title":"truncated',
                    '{"bad": [{"title":"nested fake"}]', '{"bad": invalid, "nested":{"title":"fake"}}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                extract_metadata_json(raw)

    def test_different_metadata_objects_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'multiple different'):
            extract_metadata_json('{"title":"first"}\n{"title":"second"}')

    def test_identical_repeated_metadata_is_unambiguous(self):
        self.assertEqual(extract_metadata_json('{"title":"同一本"}{"title":"同一本"}'), {'title': '同一本'})


if __name__ == '__main__':
    unittest.main()
