from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from pydantic import BaseModel

from .config import load_default_env
from .llm.base import LLMProvider
from .llm.factory import build_llm_provider
from .llm.prompts import AGENTIC_SYSTEM_PROMPT, build_agentic_user_prompt
from .llm.schemas import AgenticLLMOutput, llm_output_to_updates, parse_agentic_output
from .models import LeadData
from .pii import CPF_RE, EMAIL_RE, PHONE_RE, PLATE_RE, mask_cpf, mask_email, mask_phone


class ExtractionResult(BaseModel):
    updates: dict[str, Any]
    confidence: float = 0.8
    source: str = "deterministic"
    llm_error_type: str | None = None
    intent: str | None = None
    commercial_signals: dict[str, bool] = {}
    suggested_next_action: str | None = None
    reply_draft: str | None = None


class LeadExtractor:
    """Extrai slots de cotacao.

    O modo OpenAI e opcional. A base deterministica roda sem chave para facilitar avaliacao
    local. Quando `OPENAI_API_KEY` esta presente, o LLM complementa campos que regex nao
    pegou, mas nunca substitui validacoes criticas de payload.
    """

    VEHICLE_YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d|2050)\b")
    AGE_RE = re.compile(r"\b(?:tenho\s*)?(\d{2,3})\s*anos?\b", re.IGNORECASE)
    CEP_RE = re.compile(r"\b\d{5}-?\d{3}\b")
    DATE_BR_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
    DATE_ISO_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
    VEHICLE_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
        ("Toyota", "Corolla", re.compile(r"\b(?:toyota\s+)?corolla\b", re.IGNORECASE)),
        ("Volkswagen", "T-Cross", re.compile(r"\b(?:volkswagen|vw)?\s*t[- ]?cross\b", re.IGNORECASE)),
        ("Honda", "Civic", re.compile(r"\b(?:honda\s+)?civic\b", re.IGNORECASE)),
        ("Chevrolet", "Onix", re.compile(r"\b(?:chevrolet|gm)?\s*onix\b", re.IGNORECASE)),
        ("Hyundai", "HB20", re.compile(r"\b(?:hyundai\s+)?hb20\b", re.IGNORECASE)),
        ("Jeep", "Compass", re.compile(r"\b(?:jeep\s+)?compass\b", re.IGNORECASE)),
        ("Volkswagen", "Gol", re.compile(r"\b(?:volkswagen|vw)?\s*gol\b", re.IGNORECASE)),
    )

    def __init__(
        self,
        use_llm: bool | None = None,
        llm_provider: LLMProvider | None = None,
    ) -> None:
        load_default_env()
        if llm_provider is not None:
            self.llm_provider = llm_provider
            self.use_llm = llm_provider.name != "disabled"
        elif use_llm is True:
            self.llm_provider = build_llm_provider("auto")
            self.use_llm = True
        elif use_llm is False:
            self.llm_provider = build_llm_provider("disabled")
            self.use_llm = False
        else:
            self.llm_provider = build_llm_provider()
            self.use_llm = self.llm_provider.name != "disabled"

    def extract(self, message: str, current: LeadData | None = None) -> ExtractionResult:
        current = current or LeadData()
        updates = self._deterministic_extract(message)
        source = "deterministic"
        llm_error_type = None
        if self.use_llm:
            llm_updates, llm_error_type = self._llm_extract(message, current, updates)
            if llm_updates:
                updates = {**updates, **llm_updates}
                source = "deterministic+llm"
            elif llm_error_type:
                source = "deterministic+llm_fallback"
        return ExtractionResult(updates=updates, source=source, llm_error_type=llm_error_type)

    async def aextract(self, message: str, current: LeadData | None = None) -> ExtractionResult:
        current = current or LeadData()
        updates = self._deterministic_extract(message)
        source = "deterministic"
        llm_error_type = None
        llm_output: AgenticLLMOutput | None = None
        if self.use_llm:
            llm_updates, llm_error_type, llm_output = await self._llm_extract_async(
                message,
                current,
                updates,
            )
            if llm_updates:
                updates = {**updates, **llm_updates}
                source = "deterministic+llm"
            elif llm_error_type:
                source = "deterministic+llm_fallback"
        return ExtractionResult(
            updates=updates,
            source=source,
            llm_error_type=llm_error_type,
            intent=llm_output.intent if llm_output else None,
            commercial_signals=llm_output.commercial_signals.model_dump() if llm_output else {},
            suggested_next_action=llm_output.suggested_next_action if llm_output else None,
            reply_draft=llm_output.reply_draft if llm_output else None,
        )

    def _deterministic_extract(self, message: str) -> dict[str, Any]:
        folded = message.casefold()
        updates: dict[str, Any] = {}

        if match := self.AGE_RE.search(message):
            age = int(match.group(1))
            if 0 <= age <= 120:
                updates["idade"] = age

        if match := self.CEP_RE.search(message):
            updates["cep"] = match.group(0)

        if match := CPF_RE.search(message):
            updates["cpf_masked"] = mask_cpf(match.group(0))

        if match := EMAIL_RE.search(message):
            updates["email_masked"] = mask_email(match.group(0))

        if match := PHONE_RE.search(message):
            updates["telefone_masked"] = mask_phone(match.group(0))

        vehicle_source = self._vehicle_source_text(message)
        years = [int(y) for y in self.VEHICLE_YEAR_RE.findall(vehicle_source)]
        if years:
            updates["veiculo_ano"] = max(years)
            vehicle_text = self._vehicle_text(vehicle_source)
            if vehicle_text:
                updates["veiculo_texto"] = vehicle_text
                vehicle_parts = self._vehicle_components(vehicle_text)
                updates.update(vehicle_parts)

        plan = self._plan_from_text(folded)
        if plan:
            updates["plano_id"] = plan

        if match := self.DATE_ISO_RE.search(message):
            updates["data_inicio"] = match.group(1)
        elif match := self.DATE_BR_RE.search(message):
            day, month, year = map(int, match.groups())
            try:
                updates["data_inicio"] = date(year, month, day).isoformat()
            except ValueError:
                pass

        name = self._name_from_text(message)
        if name:
            updates["nome"] = name

        if any(
            term in folded
            for term in (
                "tanto faz",
                "voce escolhe",
                "você escolhe",
                "qual voce recomenda",
                "qual você recomenda",
            )
        ):
            updates.setdefault("plano_id", "completo")
            updates.setdefault("observacoes", []).append(
                "Cliente delegou escolha do plano; agente recomendou Completo."
            )

        return updates

    def _llm_extract(
        self,
        message: str,
        current: LeadData,
        deterministic: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        try:
            llm_updates, llm_error_type, _ = asyncio.run(
                self._llm_extract_async(message, current, deterministic)
            )
            return llm_updates, llm_error_type
        except RuntimeError as exc:
            return {}, type(exc).__name__

    async def _llm_extract_async(
        self,
        message: str,
        current: LeadData,
        deterministic: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None, AgenticLLMOutput | None]:
        try:
            parsed = await self.llm_provider.complete_json(
                system_prompt=AGENTIC_SYSTEM_PROMPT,
                user_prompt=build_agentic_user_prompt(
                    message=message,
                    current=current,
                    deterministic_updates=deterministic,
                ),
                schema_name="autoseguro_agentic_extraction",
            )
            llm_output = parse_agentic_output(parsed)
        except Exception as exc:
            return {}, type(exc).__name__, None

        return llm_output_to_updates(llm_output, deterministic), None, llm_output

    @staticmethod
    def _plan_from_text(folded: str) -> str | None:
        if "premium" in folded:
            return "premium"
        if "completo" in folded or "vidros" in folded or "terceiros" in folded:
            return "completo"
        if "essencial" in folded or "basico" in folded or "básico" in folded:
            return "essencial"
        return None

    @staticmethod
    def _vehicle_text(message: str) -> str | None:
        clean = re.sub(r"\s+", " ", message).strip(" .,!;")
        year_match = LeadExtractor.VEHICLE_YEAR_RE.search(clean)
        if not year_match:
            return None
        structured = LeadExtractor._known_vehicle_text(clean, int(year_match.group(1)))
        if structured:
            return structured
        for segment in re.split(r"[.;\n]", clean):
            if LeadExtractor.VEHICLE_YEAR_RE.search(segment):
                segment = re.split(
                    r"\b(?:e quero|quero|e queria|queria|gostaria|com inicio|com início|para inicio|para início|plano|premium|completo|essencial)\b",
                    segment,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0]
                segment = re.sub(
                    r"^.*\b(?:meu carro|carro|veiculo|veículo)\s+(?:e|é)?\s*(?:um|uma)?\s*",
                    "",
                    segment.strip(" ,.;"),
                    flags=re.IGNORECASE,
                )
                segment = re.sub(r"^(?:e|é|um|uma|de)\s+", "", segment, flags=re.IGNORECASE)
                segment = re.sub(r"\bde\s+(\d{4})\b", r"\1", segment, flags=re.IGNORECASE)
                segment = re.sub(r",?\s*\bano\s+(\d{4})\b", r" \1", segment, flags=re.IGNORECASE)
                return segment.strip(" ,.;")
        return clean[max(0, year_match.start() - 35) : min(len(clean), year_match.end() + 10)].strip(" ,.;")

    @classmethod
    def _vehicle_source_text(cls, message: str) -> str:
        text = cls.DATE_ISO_RE.sub(" ", message)
        text = cls.DATE_BR_RE.sub(" ", text)
        text = CPF_RE.sub(" ", text)
        text = EMAIL_RE.sub(" ", text)
        text = PHONE_RE.sub(" ", text)
        text = PLATE_RE.sub(" ", text)
        text = cls.CEP_RE.sub(" ", text)
        return text

    @classmethod
    def _known_vehicle_text(cls, text: str, year: int) -> str | None:
        for brand, model, pattern in cls.VEHICLE_PATTERNS:
            if pattern.search(text):
                return f"{brand} {model} {year}"
        return None

    @classmethod
    def _vehicle_components(cls, vehicle_text: str) -> dict[str, str]:
        for brand, model, pattern in cls.VEHICLE_PATTERNS:
            if pattern.search(vehicle_text):
                return {"veiculo_marca": brand, "veiculo_modelo": model}
        without_year = cls.VEHICLE_YEAR_RE.sub("", vehicle_text).strip(" ,.;")
        without_year = re.sub(r"\bano\b", "", without_year, flags=re.IGNORECASE)
        without_year = re.sub(r"[,;]+", " ", without_year)
        without_year = re.sub(r"\s+", " ", without_year).strip()
        tokens = without_year.split()
        if len(tokens) >= 2:
            return {"veiculo_marca": tokens[0], "veiculo_modelo": " ".join(tokens[1:])}
        if len(tokens) == 1:
            return {"veiculo_modelo": tokens[0]}
        return {}

    @staticmethod
    def _name_from_text(message: str) -> str | None:
        match = re.search(
            r"\b(?:me chamo|sou|meu nome e|meu nome é)\s+"
            r"([A-ZÁÉÍÓÚÃÕÂÊÔÇ][\wÁÉÍÓÚÃÕÂÊÔÇáéíóúãõâêôç]+"
            r"(?:\s+[A-ZÁÉÍÓÚÃÕÂÊÔÇ][\wÁÉÍÓÚÃÕÂÊÔÇáéíóúãõâêôç]+){0,3})",
            message,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).strip()
        return None
