from __future__ import annotations

from typing import Any

from .models import ConversationState


def build_handoff_packet(state: ConversationState) -> dict[str, Any]:
    """Monta um pacote acionavel para o humano continuar o atendimento.

    O objetivo e transformar o estado tecnico do agente em um artefato de
    operacao comercial: o corretor sabe o que ocorreu, quais dados ja existem,
    qual foi a decisao e qual e a proxima melhor acao.
    """
    lead = state.lead
    quote_result = state.quote_result
    quote = quote_result.quote if quote_result else None
    return {
        "conversation_id": state.conversation_id,
        "trace_id": state.trace_id,
        "handoff_reason": state.handoff_reason,
        "lead": {
            "nome": lead.nome,
            "idade": lead.idade,
            "cpf_masked": lead.cpf_masked,
            "email_masked": lead.email_masked,
            "telefone_masked": lead.telefone_masked,
            "cep": lead.cep,
        },
        "vehicle": {
            "texto": lead.veiculo_texto,
            "marca": lead.veiculo_marca,
            "modelo": lead.veiculo_modelo,
            "ano": lead.veiculo_ano,
        },
        "commercial_context": {
            "plano_id": lead.plano_id,
            "data_inicio": lead.data_inicio,
            "observacoes": lead.observacoes,
            "missing_slots": state.missing_required_slots(),
        },
        "quote": {
            "status": quote_result.status if quote_result else None,
            "reason": quote_result.reason if quote_result else None,
            "plano_nome": quote.get("plano_nome") if quote else None,
            "premio_mensal": quote.get("premio_mensal") if quote else None,
            "premio_mensal_estimado": quote.get("premio_mensal_estimado") if quote else None,
            "premio_mensal_faixa": quote.get("premio_mensal_faixa") if quote else None,
            "estimated": quote.get("estimated") if quote else None,
            "requires_human_validation": quote.get("requires_human_validation") if quote else None,
            "franquia": quote.get("franquia") if quote else None,
            "coberturas": quote.get("coberturas") if quote else None,
            "pro_rata": quote.get("primeiro_pagamento_pro_rata") if quote else None,
            "attempts": [attempt.model_dump() for attempt in quote_result.attempts]
            if quote_result
            else [],
        },
        "next_best_action": _next_best_action(state),
        "summary": _summary(state),
    }


def _next_best_action(state: ConversationState) -> str:
    reason = (state.handoff_reason or "").casefold()
    if "indisponivel" in reason or "legado" in reason:
        return "Validar a estimativa/reprocessar cotacao quando o legado estabilizar e avisar o lead."
    if "recusada" in reason:
        return "Explicar criterio de recusa e avaliar alternativa comercial permitida."
    if "objecao" in reason or "negociacao" in reason:
        return "Tratar objecao comercial, comparar franquia/coberturas e tentar retenção."
    if "aceitou" in reason or "emissao" in reason:
        return "Assumir emissao da proposta, confirmar dados finais e gerar proximo passo comercial."
    if "recusou" in reason:
        return "Registrar perda ou acionar retencao com proposta alternativa permitida."
    if "midia" in reason:
        return "Solicitar transcricao/resumo do anexo ou analisar manualmente a midia recebida."
    if "humano" in reason:
        return "Assumir conversa diretamente, mantendo contexto coletado."
    return "Revisar contexto e continuar atendimento pelo canal humano."


def _summary(state: ConversationState) -> str:
    lead = state.lead
    parts = []
    if lead.nome:
        parts.append(f"Lead {lead.nome}")
    if lead.idade:
        parts.append(f"{lead.idade} anos")
    if lead.veiculo_texto:
        parts.append(f"veiculo {lead.veiculo_texto}")
    elif lead.veiculo_ano:
        parts.append(f"veiculo ano {lead.veiculo_ano}")
    if lead.cep:
        parts.append(f"CEP {lead.cep}")
    if lead.plano_id:
        parts.append(f"plano {lead.plano_id}")
    base = ", ".join(parts) if parts else "Lead com dados parciais"
    if state.quote_result and state.quote_result.status == "success":
        quote = state.quote_result.quote or {}
        return (
            f"{base}. Cotacao calculada: {quote.get('plano_nome')} por "
            f"R$ {quote.get('premio_mensal')}/mes."
        )
    if state.quote_result and state.quote_result.status == "estimated":
        quote = state.quote_result.quote or {}
        faixa = quote.get("premio_mensal_faixa") or {}
        return (
            f"{base}. Estimativa preliminar: {quote.get('plano_nome')} entre "
            f"R$ {faixa.get('min')} e R$ {faixa.get('max')}/mes, pendente de validacao humana."
        )
    if state.handoff_reason:
        return f"{base}. Encaminhado para humano: {state.handoff_reason}."
    return base + "."
