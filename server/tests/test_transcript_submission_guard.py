import unittest

from server.transcript import assess_submitted_transcript


class TranscriptSubmissionGuardTests(unittest.TestCase):
    def test_rejects_tiny_fragment(self):
        accepted, message = assess_submitted_transcript("You", "Tell me about a project you are proud of.")
        self.assertFalse(accepted)
        self.assertIn("fragment", message.lower())

    def test_rejects_interviewer_echo_prefix(self):
        accepted, message = assess_submitted_transcript(
            "tell me about",
            "Tell me about a project where you improved reliability.",
        )
        self.assertFalse(accepted)
        self.assertIn("audio", message.lower())

    def test_accepts_substantive_answer(self):
        accepted, message = assess_submitted_transcript(
            "I built a FastAPI service for interview practice and added retry-safe background evaluation.",
            "Describe a backend project you built recently.",
        )
        self.assertTrue(accepted)
        self.assertIsNone(message)


if __name__ == "__main__":
    unittest.main()
