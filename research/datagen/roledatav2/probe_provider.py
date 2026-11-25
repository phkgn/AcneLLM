"""Kiểm một provider OpenAI-compatible có chạy được với roledatav2 không.

Chạy TRƯỚC khi generate. Nó kiểm đúng những gì pipeline thật sự dùng, không phải
"gọi thử một câu cho vui" — mỗi mục dưới đây tương ứng một chỗ pipeline sẽ chết.

    python -m datagen.roledatav2.probe_provider \
        --base-url https://api.tokenrouter.com/v1 \
        --model moonshotai/kimi-k3-free \
        --api-key sk-...

Không truyền cờ thì đọc OPENAI_BASE_URL / OPENAI_MODEL / OPENAI_API_KEY trong .env.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, critical: bool = True):
    def wrapper(fn):
        def run(*args, **kwargs):
            started = time.time()
            try:
                detail = fn(*args, **kwargs) or ""
                RESULTS.append((name, True, f"{detail} [{time.time() - started:.1f}s]"))
                print(f"  [OK]   {name}: {detail} ({time.time() - started:.1f}s)")
                return True
            except Exception as exc:
                mark = "FAIL" if critical else "warn"
                RESULTS.append((name, not critical, f"{type(exc).__name__}: {exc}"))
                print(f"  [{mark}] {name}: {type(exc).__name__}: {str(exc)[:300]}")
                return False

        return run

    return wrapper


def build_client(base_url: str, api_key: str):
    from openai import OpenAI

    return OpenAI(base_url=base_url, api_key=api_key, timeout=120.0, max_retries=0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL"))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY"))
    parser.add_argument("--concurrency", type=int, default=12, help="mức song song pipeline sẽ dùng")
    args = parser.parse_args(argv)

    if not (args.base_url and args.model and args.api_key):
        # Rơi về .env của repo qua chính Config của module.
        from .config import Config

        cfg = Config()
        args.base_url = args.base_url or cfg.base_url
        args.model = args.model or cfg.model
        args.api_key = args.api_key or cfg.api_key
    if not args.api_key:
        print("Thiếu API key.")
        return 2

    print(f"provider : {args.base_url}")
    print(f"model    : {args.model}\n")
    client = build_client(args.base_url, args.api_key)

    @check("chat non-stream (cách pipeline gọi)")
    def chat_basic() -> str:
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "Trả lời ngắn gọn bằng tiếng Việt."},
                {"role": "user", "content": "Bạn là model gì?"},
            ],
            max_tokens=120,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise ValueError("trả về rỗng")
        return text[:90].replace("\n", " ")

    @check("models.retrieve (preflight probe)", critical=False)
    def models_retrieve() -> str:
        return client.models.retrieve(args.model).id

    @check("response_format=json_object (BẮT BUỘC)")
    def json_mode() -> str:
        """Phân biệt 3 kiểu hỏng, vì cách sửa khác hẳn nhau.

        (a) provider từ chối tham số  -> đổi provider hoặc bỏ JSON mode
        (b) JSON bị CẮT giữa chừng    -> nới max_tokens / provider cắt output
        (c) JSON sai cú pháp          -> model yếu, phải nới parser
        """
        try:
            response = client.chat.completions.create(
                model=args.model,
                messages=[
                    {"role": "system", "content": "Chỉ xuất đúng một JSON object, không Markdown."},
                    {
                        "role": "user",
                        "content": 'Xuất {"user":"câu hỏi về mụn","assistant":"câu trả lời ngắn",'
                        '"points":["ý 1","ý 2"],"input_style":"standard","audience":"general"}',
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=1500,
            )
        except Exception as exc:
            raise RuntimeError(f"(a) provider TỪ CHỐI response_format: {exc}") from exc

        content = response.choices[0].message.content or ""
        finish = response.choices[0].finish_reason
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            kind = "(b) JSON bị CẮT" if finish == "length" else "(c) JSON sai cú pháp"
            raise RuntimeError(
                f"{kind} · finish_reason={finish} · {len(content)} ký tự · "
                f"lỗi={exc} · đuôi={content[-60:]!r}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError("không phải JSON object")
        return f"finish={finish} · khoá: {sorted(payload)}"

    @check("sinh câu trả lời dài 1.100-1.600 ký tự, có cấu trúc")
    def long_structured() -> str:
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "Chỉ xuất đúng một JSON object."},
                {
                    "role": "user",
                    "content": (
                        "Viết mẫu tư vấn da mụn tiếng Việt. Câu trả lời khoảng 1350 ký tự, "
                        "phủ ít nhất 3 ý riêng biệt, trình bày thành gạch đầu dòng. "
                        'Xuất {"user":"...","assistant":"...","points":["...","...","..."]}'
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=1200,
        )
        payload = json.loads(response.choices[0].message.content or "")
        answer = str(payload.get("assistant", ""))
        bullets = sum(1 for line in answer.splitlines() if line.strip()[:2] in {"- ", "* "} or line.strip()[:2].rstrip(".").isdigit())
        points = len(payload.get("points") or [])
        if len(answer) < 800:
            raise ValueError(f"chỉ ra {len(answer)} ký tự — quá ngắn cho band 1.100-1.600")
        return f"{len(answer)} ký tự, {bullets} gạch đầu dòng, {points} points"

    @check("trả lời 100% tiếng Việt khi tài liệu là tiếng Anh")
    def vietnamese_from_english() -> str:
        response = client.chat.completions.create(
            model=args.model,
            messages=[
                {"role": "system", "content": "Chỉ xuất đúng một JSON object."},
                {
                    "role": "user",
                    "content": (
                        "TÀI LIỆU (tiếng Anh): 'Offer a 12-week course of topical benzoyl peroxide "
                        "as monotherapy for mild to moderate acne. Review at 12 weeks.'\n"
                        "Viết câu hỏi + câu trả lời TIẾNG VIỆT bám tài liệu này, không chèn tiếng Anh. "
                        'Xuất {"user":"...","assistant":"..."}'
                    ),
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        answer = str(json.loads(response.choices[0].message.content or "").get("assistant", ""))
        diacritics = set("ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
        ratio = sum(1 for char in answer if char in diacritics) / max(len(answer), 1)
        if ratio < 0.02:
            raise ValueError(f"tỉ lệ dấu tiếng Việt {ratio:.3f} — nghi trả lời tiếng Anh")
        return f"tỉ lệ dấu {ratio:.3f}, {len(answer)} ký tự"

    @check("thông lượng: có kịp sinh 1.400 ký tự trong timeout không")
    def throughput() -> str:
        started = time.time()
        response = client.chat.completions.create(
            model=args.model,
            messages=[{"role": "user", "content": "Viết đúng 400 ký tự tiếng Việt về chăm sóc da mụn."}],
            max_tokens=400,
        )
        elapsed = time.time() - started
        chars = len(response.choices[0].message.content or "")
        rate = chars / max(elapsed, 0.01)
        eta = 1400 / max(rate, 0.01)
        if eta > 110:
            raise ValueError(
                f"{rate:.1f} ký tự/giây -> 1.400 ký tự mất ~{eta:.0f}s, "
                f"vượt request_timeout_s=120 của pipeline"
            )
        return f"{rate:.1f} ký tự/giây -> 1.400 ký tự ~{eta:.0f}s"

    @check(f"chịu được {args.concurrency} request song song")
    def concurrency() -> str:
        import concurrent.futures as futures

        def one(index: int) -> float:
            started = time.time()
            client.chat.completions.create(
                model=args.model,
                messages=[{"role": "user", "content": f"Đếm từ 1 đến 3. (lần {index})"}],
                max_tokens=40,
            )
            return time.time() - started

        with futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            times = list(pool.map(one, range(args.concurrency)))
        return f"{len(times)} request OK, chậm nhất {max(times):.1f}s"

    print("== KIỂM PROVIDER ==")
    ok_basic = chat_basic()
    if not ok_basic:
        print("\nKhông gọi được API cơ bản — dừng.")
        return 1
    models_retrieve()
    ok_json = json_mode()
    throughput()
    long_structured()
    vietnamese_from_english()
    concurrency()

    critical_failed = [name for name, ok, _ in RESULTS if not ok]
    print("\n== KẾT LUẬN ==")
    if not ok_json:
        print("  response_format=json_object KHÔNG chạy -> pipeline không dùng được provider này")
        print("  (cả `generate` lẫn `judge_knowledge` đều dựa vào JSON mode)")
    if critical_failed:
        print(f"  Hỏng: {', '.join(critical_failed)}")
        return 1
    print("  Provider dùng được. Đặt vào .env:")
    print(f"    OPENAI_BASE_URL={args.base_url}")
    print(f"    OPENAI_MODEL={args.model}")
    print("    OPENAI_API_KEY=<khoá>")
    print("    OPENAI_INPUT_PRICE_PER_MILLION=0     # model free -> để 0")
    print("    OPENAI_OUTPUT_PRICE_PER_MILLION=0")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
