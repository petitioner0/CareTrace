from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from .config import settings
from .schemas import CandidateBatch, CandidateFact


class LLMProvider(ABC):
    @abstractmethod
    def extract(self, sources: dict[str, str]) -> CandidateBatch:
        raise NotImplementedError


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


class FixtureProvider(LLMProvider, EmbeddingProvider):
    """Deterministic provider for tests and an explicitly selected offline demo."""

    def extract(self, sources: dict[str, str]) -> CandidateBatch:
        facts: list[CandidateFact] = []
        for source_ref, text in sources.items():
            for sentence in _sentences(text):
                lower = sentence.lower()
                entity_type = None
                if "allerg" in lower:
                    entity_type = "allergy"
                elif re.search(r"\b\d+\s*mg\b", lower):
                    entity_type = "dosage"
                elif "medication" in lower or "metformin" in lower:
                    entity_type = "medication"
                elif "critical action:" in lower:
                    entity_type = "critical_action"
                elif any(term in lower for term in ("follow-up", "follow up", "lab order", "waiting")):
                    entity_type = "task"
                elif any(term in lower for term in ("symptom", "plan", "complaint")):
                    entity_type = "clinical_entity"
                if not entity_type:
                    continue
                normalized = re.sub(r"\s+", " ", sentence).strip().lower()
                facts.append(
                    CandidateFact(
                        source_ref=source_ref,
                        evidence_quote=sentence,
                        normalized_value=normalized,
                        entity_type=entity_type,
                        candidate_summary=sentence,
                    )
                )
        return CandidateBatch(facts=facts)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * 24
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                digest = hashlib.sha256(token.encode()).digest()
                vector[digest[0] % len(vector)] += 1 if digest[1] % 2 else -1
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class OllamaProvider(LLMProvider, EmbeddingProvider):
    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{settings.ollama_base_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError("ollama_unavailable") from exc

    def extract(self, sources: dict[str, str]) -> CandidateBatch:
        schema = CandidateBatch.model_json_schema()
        source_text = "\n\n".join(f"SOURCE {key}\n{text}" for key, text in sources.items())
        prompt = (
            "Extract only source-supported clinical facts. evidence_quote must be copied verbatim from the "
            "identified source. Never return character offsets. Do not diagnose or infer risk. "
            "Return an empty facts array when evidence is insufficient.\n\n" + source_text
        )
        result = self._post(
            "/api/chat",
            {
                "model": settings.ollama_chat_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
            },
        )
        return CandidateBatch.model_validate_json(result["message"]["content"])

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self._post("/api/embed", {"model": settings.ollama_embed_model, "input": texts})
        return result["embeddings"]


def get_provider() -> LLMProvider & EmbeddingProvider:
    if settings.ai_provider == "fixture":
        return FixtureProvider()
    if settings.ai_provider == "ollama":
        return OllamaProvider()
    raise RuntimeError(f"Unsupported AI_PROVIDER: {settings.ai_provider}")
