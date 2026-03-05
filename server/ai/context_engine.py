from __future__ import annotations


class ContextEngine:
    def __init__(self) -> None:
        self.transcripts: list[str] = []

    def update(self, text: str) -> None:
        if text:
            self.transcripts.append(text)
            if len(self.transcripts) > 50:
                self.transcripts = self.transcripts[-50:]

    def recent_text(self, count: int = 5) -> str:
        return " ".join(self.transcripts[-count:]).strip()
