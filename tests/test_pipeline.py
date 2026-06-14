"""특성화/회귀 테스트 — pipeline.py의 결정적 순수 함수.

LLM 호출·NLM CLI·subprocess·대화형 TUI는 단위 테스트 대상에서 제외
(네트워크·API 키·Chrome 의존). 입력→출력이 결정적인 코어만 검증한다.

실행: .venv/bin/python3 -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline  # noqa: E402


class TestSafeJson(unittest.TestCase):
    def test_plain_valid_json(self):
        self.assertEqual(pipeline.safe_json('{"a": 1, "b": [2, 3]}'),
                         {"a": 1, "b": [2, 3]})

    def test_code_fenced_json(self):
        raw = '```json\n{"name": "The AI Vet"}\n```'
        self.assertEqual(pipeline.safe_json(raw), {"name": "The AI Vet"})

    def test_json_embedded_in_prose(self):
        raw = '아래가 결과입니다:\n{"score": 7}\n참고하세요.'
        self.assertEqual(pipeline.safe_json(raw), {"score": 7})

    def test_truncated_json_is_repaired(self):
        # LLM 출력이 max_tokens에서 잘린 경우 — 닫힘 괄호 보정 기대
        raw = '{"ideas": [{"t": "a"}, {"t": "b"}'
        out = pipeline.safe_json(raw)
        self.assertEqual(out.get("ideas", [])[0], {"t": "a"})

    def test_garbage_returns_empty_dict(self):
        self.assertEqual(pipeline.safe_json("완전히 깨진 텍스트 no json"), {})


class TestStripAnsi(unittest.TestCase):
    def test_removes_color_codes(self):
        self.assertEqual(pipeline.strip_ansi("\x1b[92m✓ ok\x1b[0m"), "✓ ok")

    def test_plain_text_unchanged(self):
        self.assertEqual(pipeline.strip_ansi("no codes here"), "no codes here")


class TestDebateMemory(unittest.TestCase):
    def test_add_records_turn(self):
        m = pipeline.DebateMemory()
        m.add("Champion 1", "옹호", "아이디어 A가 최고")
        self.assertEqual(len(m.turns), 1)
        self.assertEqual(m.turns[0]["agent"], "Champion 1")

    def test_last_n_returns_only_recent(self):
        m = pipeline.DebateMemory()
        for i in range(6):
            m.add(f"A{i}", "role", f"발언{i}")
        out = m.last_n(2)
        self.assertIn("발언5", out)
        self.assertNotIn("발언3", out)

    def test_conclusions_accumulate(self):
        m = pipeline.DebateMemory()
        m.add_conclusion("결론1")
        m.add_conclusion("결론2")
        self.assertEqual(m.all_conclusions(), "- 결론1\n- 결론2")
