"""Refusal phai den duoc nguoi dung KE CA khi generator chet.

Kien truc: guardrail quyet NOI DUNG (ruling), generator viet CAU CHU
(orchestrator.py:112). Hay o cho UX, nhung no bien generator thanh diem chiu
loi don cho dung cai luot ma ta khong duoc phu thuoc LLM: neu stream nem
exception giua chung, canh bao chong chi dinh bien mat va nguoi dung chi thay
"Da xay ra loi, vui long thu lai".

Test nay la ly do duy nhat biet nhanh fallback o runtime.py con song.
"""
from types import SimpleNamespace

import acne_llm.chat.runtime as runtime


_DISCLAIMER = (
    "Không sử dụng isotretinoin, retinoid hoặc kháng sinh nhóm tetracycline "
    "trong thai kỳ/cho con bú."
)


def _prepared_with_refusal():
    return SimpleNamespace(
        intake=SimpleNamespace(
            scope_refusal=SimpleNamespace(disclaimer=_DISCLAIMER),
        )
    )


def _run(monkeypatch, prepared):
    """Cho prepare_chat_turn tra ve `prepared` roi cho stream no ngay sau do."""
    monkeypatch.setattr(runtime, "prepare_chat_turn", lambda *a, **k: prepared)

    def _boom(*a, **k):
        raise RuntimeError("ollama died mid-stream")

    # Buoc than ham vao nhanh except: bat cu thu gi sau prepare_chat_turn.
    monkeypatch.setattr(runtime, "log_pipeline_stage", _boom)
    return "".join(runtime.stream_chat_sse(SimpleNamespace(), "em bị mụn", session_id=None))


def test_generator_chet_van_tra_ban_cung_cua_refusal(monkeypatch):
    out = _run(monkeypatch, _prepared_with_refusal())
    assert _DISCLAIMER in out
    assert "Đã xảy ra lỗi" not in out


def test_turn_thuong_chet_thi_van_bao_loi_nhu_cu(monkeypatch):
    out = _run(monkeypatch, SimpleNamespace(intake=SimpleNamespace(scope_refusal=None)))
    assert "Đã xảy ra lỗi" in out


def test_prepare_chet_som_khong_gay_NameError(monkeypatch):
    """`prepared` duoc gan None truoc try -- neu quen, except nem NameError."""
    def _boom(*a, **k):
        raise RuntimeError("intake died")

    monkeypatch.setattr(runtime, "prepare_chat_turn", _boom)
    out = "".join(runtime.stream_chat_sse(SimpleNamespace(), "em bị mụn", session_id=None))
    assert "Đã xảy ra lỗi" in out
