"""Mock vision — placeholder until đề tài 27 ghép vào."""
from ..schemas import VisionOutput


class MockVision:
    def analyze(self, image_bytes: bytes) -> VisionOutput:
        return VisionOutput(
            severity_estimate="moderate",
            lesion_counts={"papule": 8, "pustule": 3, "comedone": 15},
            lesions=[],
            skin_regions=["forehead", "cheek", "chin"],
            notes="mock output — đề tài 27 sẽ thay thế",
            model_name="mock-vision-v0",
            confidence=0.5,
        )
