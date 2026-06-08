from __future__ import annotations

import ddddocr

_ocr: ddddocr.DdddOcr | None = None


def get_ocr() -> ddddocr.DdddOcr:
    global _ocr
    if _ocr is None:
        _ocr = ddddocr.DdddOcr(show_ad=False)
    return _ocr


def recognize_digits(image_bytes: bytes, expected_len: int = 4) -> str | None:
    code = get_ocr().classification(image_bytes)
    code = (code or "").strip()
    if len(code) == expected_len and code.isdigit():
        return code
    return None
