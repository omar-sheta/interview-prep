import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch

from server.agents import nodes
from server.services import vector_service
from server.services.vector_service import match_skills_semantically
from server.tools import resume_tool


class ResumeAnalysisPipelineTests(unittest.TestCase):
    def test_extract_text_from_pdf_bytes_falls_back_to_pypdf(self):
        class FakePage:
            def extract_text(self):
                return "Fallback page text"

        class FakeReader:
            def __init__(self, _file_obj):
                self.pages = [FakePage()]

        with patch.object(resume_tool, "fitz", None), \
             patch.object(resume_tool, "PdfReader", FakeReader):
            text = resume_tool.extract_text_from_pdf_bytes(b"fake pdf")

        self.assertIn("Fallback page text", text)

    def test_match_skills_semantically_finds_close_match(self):
        with patch.object(vector_service, "_get_embedder", return_value=None):
            matches = match_skills_semantically(
                candidate_skills=["Python", "Distributed Systems", "Kubernetes"],
                required_skills=["python", "kubernetes orchestration"],
                threshold=0.4,
            )
        self.assertIn("python", matches)
        self.assertEqual(matches["python"]["candidate_skill"], "Python")
        self.assertIn("kubernetes orchestration", matches)

    def test_canonical_skill_name_handles_suffix_variants(self):
        self.assertEqual(nodes._canonical_skill_name("Kubernetes Orchestration"), "kubernetes")
        self.assertEqual(nodes._canonical_skill_name("CI CD Pipeline"), "ci/cd")
        self.assertEqual(nodes._canonical_skill_name("System Architecture"), "system design")

    def test_build_skill_coverage_board_missing_skill_uses_20_percent_floor(self):
        required = nodes._normalize_required_skill_rows([
            {
                "skill": "Go Programming Language",
                "priority": "must_have",
                "required_level": "intermediate",
                "importance": 0.9,
            }
        ])
        coverage = nodes._build_skill_coverage_board(required, candidate_skills=[])
        board = coverage.get("board", [])
        self.assertEqual(len(board), 1)
        self.assertEqual(board[0]["status"], "Missing")
        self.assertAlmostEqual(board[0]["confidence"], 0.2, places=2)

    def test_semantic_candidate_rows_support_partial_confidence_band(self):
        rows = resume_tool._semantic_candidate_rows(
            {
                "System Design": {
                    "candidate_skill": "System Architecture",
                    "score": 0.64,
                }
            }
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["skill"], "System Design")
        self.assertEqual(row["candidate_level"], "basic")
        self.assertGreaterEqual(float(row["confidence"]), 0.3)
        self.assertLessEqual(float(row["confidence"]), 0.45)
        self.assertIn("System Architecture", row["evidence"][0])

    def test_analyze_resume_and_job_returns_pipeline_result(self):
        expected = {
            "personal_info": {"name": "Ada Lovelace"},
            "summary": "Backend engineer.",
            "skills": {
                "hard_skills": ["Python"],
                "tools_and_tech": ["Docker"],
                "soft_skills": ["Communication"],
                "certifications": [],
            },
            "experience": [],
            "education": [],
            "years_of_experience": 6,
            "job_requirements": {
                "must_have_skills": ["Python"],
                "nice_to_have_skills": ["Docker"],
                "core_responsibilities": ["Build services"],
                "career_level": "senior",
                "interview_focus_areas": ["Coding"],
            },
            "skill_analysis": [],
            "readiness_score": 0.82,
            "top_gaps": [],
        }

        with patch("server.tools.resume_tool._run_resume_analysis_pipeline", new=AsyncMock(return_value=(expected, {"skill_mapping": {}}))):
            result = asyncio.run(
                resume_tool.analyze_resume_and_job(
                    resume_text="Ada resume text",
                    job_title="Senior Software Engineer",
                    company="Google",
                    job_description="Python and Docker",
                )
            )

        self.assertEqual(result["personal_info"]["name"], "Ada Lovelace")
        self.assertEqual(result["readiness_score"], 0.82)
        self.assertEqual(result["job_requirements"]["career_level"], "senior")

    def test_pipeline_uses_holistic_trial_when_flag_enabled(self):
        trial_result = {
            "personal_info": {"name": "Omar Sheta"},
            "summary": "Strong fit for AI safety research internships.",
            "skills": {
                "hard_skills": ["Python", "Large Language Models", "AI Safety"],
                "tools_and_tech": ["PyTorch", "Docker"],
                "soft_skills": ["Communication"],
                "certifications": [],
            },
            "experience": [],
            "education": [],
            "years_of_experience": 3,
            "job_requirements": {
                "must_have_skills": ["Python", "Large Language Models", "AI Safety"],
                "nice_to_have_skills": ["RAG"],
                "core_responsibilities": ["Research reliable AI systems"],
                "career_level": "entry",
                "interview_focus_areas": ["AI reliability", "Research communication"],
            },
            "skill_analysis": [
                {
                    "skill": "Python",
                    "priority": "must_have",
                    "status": "strong_match",
                    "candidate_level": "advanced",
                    "required_level": "intermediate",
                    "evidence": "Technical skills list includes Python.",
                    "confidence": 0.92,
                },
                {
                    "skill": "Large Language Models",
                    "priority": "must_have",
                    "status": "strong_match",
                    "candidate_level": "advanced",
                    "required_level": "intermediate",
                    "evidence": "Research focus and projects center on LLM safety.",
                    "confidence": 0.9,
                },
            ],
            "readiness_score": 0.84,
            "top_gaps": ["RAG"],
        }

        with patch.object(resume_tool.settings, "RESUME_ANALYSIS_SINGLE_LLM_TRIAL", True), \
             patch("server.tools.resume_tool._run_holistic_resume_analysis_trial", new=AsyncMock(return_value=(trial_result, resume_tool._details_from_single_call_result(trial_result, "AI Security Researcher", "Microsoft")))):
            result, details = asyncio.run(
                resume_tool._run_resume_analysis_pipeline(
                    resume_text="resume",
                    job_title="AI Security Researcher",
                    company="Microsoft",
                    job_description="Research AI reliability.",
                )
            )

        self.assertEqual(result["personal_info"]["name"], "Omar Sheta")
        self.assertEqual(details["skill_mapping"]["matched"][0]["name"], "Python")
        self.assertGreater(details["readiness_score"], 0.8)

    def test_holistic_trial_uses_json_schema(self):
        fake_response = type("FakeResponse", (), {"content": """{
            "personal_info": {"name": "Omar Sheta", "email": "", "phone": "", "location": ""},
            "summary": "Good fit.",
            "skills": {"hard_skills": ["Python"], "tools_and_tech": ["PyTorch"], "soft_skills": ["Communication"], "certifications": []},
            "experience": [],
            "education": [],
            "years_of_experience": 3,
            "job_requirements": {"must_have_skills": ["Python"], "nice_to_have_skills": [], "core_responsibilities": ["Research"], "career_level": "entry", "interview_focus_areas": ["Python"]},
            "skill_analysis": [{"skill": "Python", "priority": "must_have", "status": "strong_match", "candidate_level": "advanced", "required_level": "intermediate", "evidence": "Listed in technical skills.", "confidence": 0.91}],
            "readiness_score": 0.83,
            "top_gaps": []
        }"""})()

        fake_model = type("FakeModel", (), {"ainvoke": AsyncMock(return_value=fake_response)})()

        with patch("server.tools.resume_tool.get_chat_model", return_value=fake_model):
            result, details = asyncio.run(
                resume_tool._run_holistic_resume_analysis_trial(
                    resume_text="resume",
                    job_title="AI Security Researcher",
                    company="Microsoft",
                    job_description="Python research internship",
                )
            )

        self.assertEqual(result["personal_info"]["name"], "Omar Sheta")
        self.assertIn("json_schema", fake_model.ainvoke.await_args.kwargs)
        self.assertTrue(details["skill_mapping"]["matched"])

    def test_analyze_career_path_uses_pipeline_details(self):
        result_payload = {
            "personal_info": {"name": "Grace Hopper"},
            "summary": "Platform engineer.",
            "skills": {
                "hard_skills": ["Python"],
                "tools_and_tech": ["Docker"],
                "soft_skills": ["Leadership"],
                "certifications": [],
            },
            "experience": [],
            "education": [],
            "years_of_experience": 8,
            "job_requirements": {
                "must_have_skills": ["Python", "System Design"],
                "nice_to_have_skills": ["Kubernetes"],
                "core_responsibilities": ["Build systems"],
                "career_level": "senior",
                "interview_focus_areas": ["System design"],
            },
            "skill_analysis": [],
            "readiness_score": 0.72,
            "top_gaps": ["System Design"],
        }
        details = {
            "resume_data": {
                "summary": "Platform engineer.",
                "skills": {
                    "hard_skills": ["Python"],
                    "tools_and_tech": ["Docker"],
                    "soft_skills": ["Leadership"],
                    "certifications": [],
                },
            },
            "job_requirements": {
                "job_title": "Senior Software Engineer",
                "company": "Google",
                "must_have_skills": ["Python", "System Design"],
                "nice_to_have_skills": ["Kubernetes"],
                "core_responsibilities": ["Build systems"],
                "career_level": "senior",
                "interview_focus_areas": ["System design"],
            },
            "skill_mapping": {
                "matched": [{"name": "Python", "status": "meets"}],
                "partial": [{
                    "name": "Kubernetes",
                    "status": "borderline",
                    "priority": "nice_to_have",
                    "reason": "Used lightly in one project.",
                    "learning_tip": "Deploy a service and debug one failure.",
                    "candidate_level": "basic",
                    "required_level": "basic",
                    "confidence": 0.58,
                }],
                "missing": [{
                    "name": "System Design",
                    "status": "missing",
                    "priority": "must_have",
                    "reason": "No architecture examples found.",
                    "learning_tip": "Practice one architecture trade-off write-up each week.",
                    "candidate_level": "none",
                    "required_level": "advanced",
                    "confidence": 0.12,
                }],
                "followup_targets": [{
                    "name": "System Design",
                    "status": "missing",
                    "priority": "must_have",
                    "reason": "No architecture examples found.",
                    "learning_tip": "Practice one architecture trade-off write-up each week.",
                    "candidate_level": "none",
                    "required_level": "advanced",
                    "confidence": 0.12,
                }],
                "followup_questions": [{
                    "skill": "System Design",
                    "question": "Explain a trade-off in a service architecture.",
                    "intent": "Validate architecture depth.",
                }],
            },
            "readiness_score": 0.72,
            "skill_gaps": [{
                "name": "System Design",
                "status": "missing",
                "priority": "must_have",
                "reason": "No architecture examples found.",
                "learning_tip": "Practice one architecture trade-off write-up each week.",
                "candidate_level": "none",
                "required_level": "advanced",
                "confidence": 0.12,
            }],
        }

        async def fake_generate_mindmap_node(state):
            return {**state, "mindmap": "flowchart TD"}

        with patch("server.tools.resume_tool._run_resume_analysis_pipeline", new=AsyncMock(return_value=(result_payload, details))), \
             patch("server.agents.nodes.generate_mindmap_node", new=AsyncMock(side_effect=fake_generate_mindmap_node)):
            state = asyncio.run(
                nodes.analyze_career_path(
                    resume_text="Grace Hopper\nPython\nDocker",
                    target_role="Senior Software Engineer",
                    target_company="Google",
                    job_description="Build systems with Python",
                )
            )

        self.assertEqual(round(state["readiness_score"], 2), 0.72)
        self.assertEqual(len(state["skill_mapping"]["matched"]), 1)
        self.assertEqual(state["skill_gaps"][0]["name"], "System Design")
        self.assertIn("learning_tip", state["skill_gaps"][0])
        self.assertTrue(state["suggested_sessions"])


if __name__ == "__main__":
    unittest.main()
