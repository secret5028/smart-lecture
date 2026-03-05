from __future__ import annotations


class WakeWordDetector:
    def __init__(self, wake_word: str) -> None:
        self.wake_word = wake_word

    def update_wake_word(self, new_word: str) -> None:
        self.wake_word = new_word

    def detect(self, text: str) -> dict | None:
        if not text or self.wake_word not in text:
            return None

        t = text.strip()
        if any(k in t for k in ["사진", "그림", "이미지"]):
            command = "show_image"
        elif any(k in t for k in ["자세히", "상세", "원문"]):
            command = "show_detail"
        elif any(k in t for k in ["다음", "넘어가"]):
            command = "next_section"
        elif any(k in t for k in ["퀴즈", "문제", "테스트"]):
            command = "make_quiz"
        else:
            command = "unknown"

        return {"command": command, "raw": text}
