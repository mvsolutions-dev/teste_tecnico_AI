from __future__ import annotations

import json
from calendar import monthrange
from datetime import date
from pathlib import Path
from typing import Any


class QuoteEstimator:
    """Estimativa preliminar para contingencia.

    Nao substitui o legado. Serve para dar contexto ao humano ou, se o produto
    permitir no futuro, apresentar faixa nao vinculante ao lead.
    """

    def __init__(self, plans_path: str | Path | None = None) -> None:
        self.plans_path = Path(plans_path) if plans_path else _default_plans_path()

    def estimate(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        try:
            plans = json.loads(self.plans_path.read_text(encoding="utf-8"))
            quote = self._estimate_with_rules(plans, payload)
        except Exception:
            return None
        quote["estimated"] = True
        quote["confidence"] = "medium"
        quote["requires_human_validation"] = True
        quote["disclaimer"] = (
            "Estimativa preliminar gerada porque o legado de cotacao estava indisponivel. "
            "Nao deve ser tratada como preco oficial sem validacao humana."
        )
        return quote

    @staticmethod
    def _estimate_with_rules(plans: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        plano_id = (payload.get("plano_id") or "essencial").lower()
        plano = next(p for p in plans["planos"] if p["id"] == plano_id)
        regras = plans["regras"]
        idade = int(payload["idade"])
        veiculo_ano = int(payload["veiculo_ano"])
        cep = str(payload.get("cep") or "")

        m_idade = _age_multiplier(regras, idade)
        m_veiculo = _vehicle_multiplier(regras, veiculo_ano, date.today())
        m_regiao = _region_multiplier(regras, cep)
        premio = round(float(plano["base_mensal"]) * m_idade * m_veiculo * m_regiao, 2)
        lower = round(premio * 0.95, 2)
        upper = round(premio * 1.05, 2)
        quote = {
            "plano_id": plano["id"],
            "plano_nome": plano["nome"],
            "premio_mensal_estimado": premio,
            "premio_mensal_faixa": {"min": lower, "max": upper},
            "franquia": plano["franquia"],
            "coberturas": plano["coberturas"],
            "multiplicadores_estimados": {
                "faixa_etaria": m_idade,
                "idade_veiculo": m_veiculo,
                "regiao": m_regiao,
            },
            "moeda": plans["moeda"],
        }
        data_inicio = payload.get("data_inicio")
        if data_inicio:
            try:
                inicio = date.fromisoformat(str(data_inicio))
                if inicio.day != 1:
                    dias_mes = monthrange(inicio.year, inicio.month)[1]
                    dias = dias_mes - inicio.day + 1
                    quote["primeiro_pagamento_pro_rata_estimado"] = {
                        "dias_no_mes": dias_mes,
                        "dias_cobrados": dias,
                        "valor_primeiro_pagamento": round(premio * dias / dias_mes, 2),
                    }
            except ValueError:
                pass
        return quote


def _default_plans_path() -> Path:
    return Path(__file__).resolve().parents[2] / "quote-service" / "data" / "plans.json"


def _age_multiplier(regras: dict[str, Any], idade: int) -> float:
    for faixa in regras["faixa_etaria"]:
        if faixa["idade_min"] <= idade <= faixa["idade_max"]:
            if faixa.get("recusar"):
                raise ValueError(faixa["motivo"])
            return float(faixa["multiplicador"])
    raise ValueError("Idade fora das faixas aceitas.")


def _vehicle_multiplier(regras: dict[str, Any], veiculo_ano: int, today: date) -> float:
    idade_veiculo = today.year - veiculo_ano
    for faixa in regras["idade_veiculo"]:
        if faixa["anos_min"] <= idade_veiculo <= faixa["anos_max"]:
            if faixa.get("recusar"):
                raise ValueError(faixa["motivo"])
            return float(faixa["multiplicador"])
    raise ValueError("Idade do veiculo fora das faixas aceitas.")


def _region_multiplier(regras: dict[str, Any], cep: str) -> float:
    prefix = cep.replace("-", "").strip()[:2]
    regiao = regras["regiao_cep"]
    return float(regiao["multiplicador"]) if prefix in regiao["prefixos_alto_risco"] else 1.0
