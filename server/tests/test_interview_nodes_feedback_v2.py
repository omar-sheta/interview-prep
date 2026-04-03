import json
import re
import sys
import types
import unittest
import importlib
import importlib.util

# Provide lightweight stubs so this test can run even when LLM/runtime deps are absent.
try:
    importlib.import_module("langchain_core.messages")
except Exception:
    messages_mod = types.ModuleType("langchain_core.messages")

    class _Message:
        def __init__(self, content=None):
            self.content = content

    messages_mod.HumanMessage = _Message
    messages_mod.SystemMessage = _Message
    langchain_core_mod = types.ModuleType("langchain_core")
    langchain_core_mod.messages = messages_mod
    sys.modules["langchain_core"] = langchain_core_mod
    sys.modules["langchain_core.messages"] = messages_mod

try:
    importlib.import_module("server.services.llm_factory")
except Exception:
    llm_factory_mod = types.ModuleType("server.services.llm_factory")

    class _NoopModel:
        async def astream(self, _messages):
            if False:
                yield None

    llm_factory_mod.get_chat_model = lambda: _NoopModel()
    sys.modules["server.services.llm_factory"] = llm_factory_mod

try:
    importlib.import_module("server.tools.resume_tool")
except Exception:
    resume_tool_mod = types.ModuleType("server.tools.resume_tool")
    resume_tool_mod.parse_json_safely = lambda text: json.loads(text) if isinstance(text, str) and text.strip().startswith("{") else {"questions": []}
    resume_tool_mod.re = re
    sys.modules["server.tools.resume_tool"] = resume_tool_mod

if importlib.util.find_spec("pydantic_settings") is None and "server.config" not in sys.modules:
    config_mod = types.ModuleType("server.config")
    config_mod.settings = types.SimpleNamespace(FEEDBACK_LOOP_V2=True)
    sys.modules["server.config"] = config_mod

from server.agents import interview_nodes as nodes


class FeedbackLoopV2EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.prev_flag = nodes.settings.FEEDBACK_LOOP_V2
        nodes.settings.FEEDBACK_LOOP_V2 = True

    def tearDown(self):
        nodes.settings.FEEDBACK_LOOP_V2 = self.prev_flag

    @staticmethod
    def _base_evaluation(score=8.5):
        return {
            "score": score,
            "score_breakdown": {
                "clarity": score,
                "accuracy": score,
                "completeness": score,
                "structure": score,
            },
            "strengths": ["Attempted answer"],
            "missing_concepts": [],
            "coaching_tip": "",
            "optimized_answer": "",
            "feedback": "",
        }

    def test_low_relevance_caps_accuracy(self):
        payload = nodes._normalize_evaluation_payload(
            evaluation=self._base_evaluation(9.0),
            expected_points=["API gateway", "load balancing", "database sharding"],
            question_text="How would you design a scalable API?",
            answer_text="I usually enjoy hiking and cooking after work on weekends.",
        )

        self.assertLessEqual(payload["score_breakdown"]["accuracy"], 3.0)
        self.assertIn("low_relevance", payload["quality_flags"])

    def test_high_repetition_caps_clarity(self):
        repetitive_answer = (
            "system system system system system system design design design design design "
            "system system system system system"
        )
        payload = nodes._normalize_evaluation_payload(
            evaluation=self._base_evaluation(8.5),
            expected_points=["system design", "trade-offs", "availability"],
            question_text="How do you design resilient distributed systems?",
            answer_text=repetitive_answer,
        )

        self.assertLessEqual(payload["score_breakdown"]["clarity"], 3.0)
        self.assertIn("high_repetition", payload["quality_flags"])

    def test_low_coverage_caps_completeness(self):
        payload = nodes._normalize_evaluation_payload(
            evaluation=self._base_evaluation(8.5),
            expected_points=["root cause", "mitigation", "impact", "prevention"],
            question_text="How did you handle an outage?",
            answer_text="I said we had an issue and then fixed something quickly.",
        )

        self.assertLessEqual(payload["score_breakdown"]["completeness"], 4.0)

    def test_weak_structure_caps_structure(self):
        payload = nodes._normalize_evaluation_payload(
            evaluation=self._base_evaluation(8.0),
            expected_points=["context", "action", "result"],
            question_text="Tell me about a difficult decision.",
            answer_text="It happened fast and I just did it",
        )

        self.assertLessEqual(payload["score_breakdown"]["structure"], 4.0)

    def test_low_transcript_quality_penalty_and_confidence(self):
        payload = nodes._normalize_evaluation_payload(
            evaluation=self._base_evaluation(6.0),
            expected_points=["context", "decision", "outcome"],
            question_text="Describe a system decision.",
            answer_text="zzzz qqqq zzzz qqqq zzzz qqqq",
        )

        self.assertIn("low_transcript_quality", payload["quality_flags"])
        self.assertLessEqual(payload["confidence"], 0.45)
        self.assertLess(payload["score"], 6.0)

    def test_normalized_payload_contains_v2_contract_keys(self):
        payload = nodes._normalize_evaluation_payload(
            evaluation=self._base_evaluation(7.0),
            expected_points=["context", "action", "outcome"],
            question_text="Tell me about leading a team.",
            answer_text="I led a team, set priorities, and delivered a release with measurable impact.",
        )

        required_keys = {
            "evaluation_version",
            "quality_flags",
            "confidence",
            "rubric_hits",
            "rubric_misses",
            "evidence_quotes",
            "improvement_plan",
            "retry_drill",
            "score",
            "score_breakdown",
            "strengths",
            "missing_concepts",
            "coaching_tip",
            "optimized_answer",
            "feedback",
        }
        self.assertTrue(required_keys.issubset(set(payload.keys())))
        self.assertEqual(payload["evaluation_version"], "v2")

    def test_tokenizer_keeps_common_tech_terms(self):
        tokens = nodes._tokenize_words("C++ C# .NET Node.js CI/CD")
        self.assertIn("cpp", tokens)
        self.assertIn("csharp", tokens)
        self.assertIn("dotnet", tokens)
        self.assertIn("nodejs", tokens)
        self.assertIn("cicd", tokens)

    def test_custom_threshold_override_changes_caps(self):
        payload = nodes._normalize_evaluation_payload(
            evaluation=self._base_evaluation(8.0),
            expected_points=["distributed systems", "fault tolerance"],
            question_text="How do you design fault tolerant distributed systems?",
            answer_text="Short answer",
            thresholds={
                "structure_cap_weak": 2.5,
                "structure_markers_min": 3,
                "structure_sentence_cap": 3,
            },
        )
        self.assertLessEqual(payload["score_breakdown"]["structure"], 2.5)


if __name__ == "__main__":
    unittest.main()
