import unittest

from server.services.audio_service import WhisperCppStreamingProcessor


class WhisperCppGpuDetectionTests(unittest.TestCase):
    def test_successful_cuda_init_log_is_not_treated_as_failure(self):
        processor = WhisperCppStreamingProcessor()
        diag = """
        ggml_cuda_init: found 1 CUDA devices (Total VRAM: 124610 MiB):
          Device 0: NVIDIA GB10, compute capability 12.1, VMM: yes, VRAM: 124610 MiB
        whisper_backend_init_gpu: using CUDA0 backend
        """
        self.assertFalse(processor._looks_like_gpu_issue(diag))

    def test_real_cuda_error_is_treated_as_failure(self):
        processor = WhisperCppStreamingProcessor()
        diag = "CUDA error: no CUDA-capable device is detected"
        self.assertTrue(processor._looks_like_gpu_issue(diag))


if __name__ == "__main__":
    unittest.main()
