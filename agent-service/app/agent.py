from __future__ import annotations

from collections import Counter
from typing import Any

from .extraction import LeadExtractor
from .handoff_packet import build_handoff_packet
from .models import AgentStatus, ChatResponse, ConversationState, LeadData, Message, QuoteResult
from .pii import redact_text
from .quote_client import QuoteClient
from .recorder import FlightRecorder
from .store import ConversationStore, InMemoryConversationStore


class AutoSeguroAgent:
    def __init__(
        self,
        *,
        quote_client: QuoteClient,
        extractor: LeadExtractor | None = None,
        recorder: FlightRecorder | None = None,
        store: ConversationStore | None = None,
    ) -> None:
        self.quote_client = quote_client
        self.extractor = extractor or LeadExtractor()
        self.recorder = recorder or FlightRecorder()
        self.store = store or InMemoryConversationStore()
        self._metrics: Counter[str] = Counter()
        self._handoff_reasons: Counter[str] = Counter()

    async def handle(
        self,
        conversation_id: str,
        message: str,
        *,
        sender_name: str | None = None,
        message_type: str = "text",
    ) -> ChatResponse:
        if not self.store.exists(conversation_id):
            self._metrics["conversations_started"] += 1
        self._metrics["messages_received"] += 1
        state = self.store.get(conversation_id)
        redacted = redact_text(message)
        state.messages.append(Message(role="lead", content=message, redacted_content=redacted))
        self.recorder.record(
            "message_received",
            {"conversation_id": conversation_id, "trace_id": state.trace_id, "content": redacted},
        )

        if state.status == AgentStatus.HANDOFF:
            reply = (
                "Seu atendimento ja esta encaminhado para um especialista humano. "
                "Vou manter esta nova mensagem no contexto para ele continuar sem perda de historico."
            )
            return self._respond(state, reply)

        if sender_name and not state.lead.nome:
            state.lead.nome = sender_name
            self.recorder.record(
                "slot_from_metadata",
                {
                    "conversation_id": conversation_id,
                    "trace_id": state.trace_id,
                    "slot": "nome",
                    "source": "sender_name",
                },
            )

        if self._wants_human(message):
            reply = self._handoff(state, "lead pediu atendimento humano")
            return self._respond(state, reply)

        if self._unsupported_media(message, message_type):
            reply = self._handoff(state, "lead enviou midia sem conteudo textual suficiente")
            return self._respond(state, reply)

        extraction = await self.extractor.aextract(message, state.lead)
        self._merge_lead(state.lead, extraction.updates)
        self.recorder.record(
            "slots_extracted",
            {
                "conversation_id": conversation_id,
                "trace_id": state.trace_id,
                "updates": self._safe_updates(extraction.updates),
                "source": extraction.source,
                "llm_error_type": extraction.llm_error_type,
                "intent": extraction.intent,
                "commercial_signals": extraction.commercial_signals,
                "suggested_next_action": extraction.suggested_next_action,
            },
        )

        if extraction.intent == "human_request" or extraction.suggested_next_action == "handoff":
            reply = self._handoff(state, "LLM classificou pedido de atendimento humano")
            return self._respond(state, reply)

        if state.quote_result and state.quote_result.status == "success":
            reply = self._after_quote_reply(state, message)
            return self._respond(state, reply)

        missing = state.missing_required_slots()
        if missing == ["plano"]:
            state.lead.plano_id = "completo"
            note = "Plano Completo usado como recomendacao padrao quando lead nao escolheu plano."
            if note not in state.lead.observacoes:
                state.lead.observacoes.append(note)
            self.recorder.record(
                "slot_defaulted",
                {
                    "conversation_id": conversation_id,
                    "trace_id": state.trace_id,
                    "slot": "plano_id",
                    "value": "completo",
                    "reason": "unico slot faltante; plano equilibrado para cotacao inicial",
                },
            )
            missing = state.missing_required_slots()
        if missing:
            state.status = AgentStatus.COLLECTING
            reply = self._safe_llm_reply_draft(extraction.reply_draft) or self._next_question(
                state,
                missing,
            )
            return self._respond(state, reply)

        state.status = AgentStatus.QUOTING
        quote_result = await self.quote_client.quote(state.lead.quote_payload())
        state.quote_result = quote_result
        self.recorder.record(
            "quote_attempted",
            {
                "conversation_id": conversation_id,
                "trace_id": state.trace_id,
                "payload": state.lead.quote_payload(),
                "status": quote_result.status,
                "attempts": [item.model_dump() for item in quote_result.attempts],
            },
        )

        if quote_result.status == "success":
            state.status = AgentStatus.QUOTED
            reply = self._quote_success_reply(quote_result)
        elif quote_result.status == "estimated":
            reply = self._handoff(
                state,
                "legado indisponivel; estimativa preliminar gerada para validacao humana",
            )
        elif quote_result.status == "refused":
            reply = self._handoff(state, f"cotacao recusada: {quote_result.reason}")
        elif quote_result.status == "invalid":
            reply = self._handoff(state, f"payload invalido para cotacao: {quote_result.reason}")
        else:
            reply = self._handoff(state, "sistema legado de cotacao indisponivel apos retries")

        return self._respond(state, reply)

    def _respond(self, state: ConversationState, reply: str) -> ChatResponse:
        state.messages.append(Message(role="agent", content=reply, redacted_content=redact_text(reply)))
        self.store.save(state)
        self._metrics["messages_sent"] += 1
        self._metrics[f"status.{state.status.value}"] += 1
        if state.quote_result:
            self._metrics[f"quote_status.{state.quote_result.status}"] += 1
        if state.handoff_reason:
            self._metrics["handoff_total"] += 1
            self._handoff_reasons[state.handoff_reason] += 1
        self.recorder.record(
            "message_sent",
            {
                "conversation_id": state.conversation_id,
                "trace_id": state.trace_id,
                "status": state.status.value,
                "reply": redact_text(reply),
                "handoff_reason": state.handoff_reason,
            },
        )
        quote_attempts = state.quote_result.attempts if state.quote_result else []
        return ChatResponse(
            conversation_id=state.conversation_id,
            trace_id=state.trace_id,
            status=state.status,
            reply=reply,
            missing_slots=state.missing_required_slots(),
            handoff_reason=state.handoff_reason,
            quote_status=state.quote_result.status if state.quote_result else None,
            quote=state.quote_result.quote if state.quote_result else None,
            quote_attempts=quote_attempts,
            handoff_packet=build_handoff_packet(state)
            if state.status == AgentStatus.HANDOFF
            else None,
            state=state.model_dump(mode="json", exclude={"messages": {"__all__": {"content"}}}),
        )

    def metrics_snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self._metrics),
            "handoff_reasons": dict(self._handoff_reasons),
            "active_conversations": self.store.count(),
        }

    @staticmethod
    def _merge_lead(lead: LeadData, updates: dict[str, Any]) -> None:
        for key, value in updates.items():
            if key == "observacoes" and isinstance(value, list):
                for item in value:
                    if item not in lead.observacoes:
                        lead.observacoes.append(str(item))
                continue
            if hasattr(lead, key) and value not in (None, ""):
                setattr(lead, key, value)

    @staticmethod
    def _safe_updates(updates: dict[str, Any]) -> dict[str, Any]:
        safe = dict(updates)
        for key in ("cpf", "cpf_masked", "email", "email_masked", "telefone", "telefone_masked"):
            if key in safe:
                safe[key] = redact_text(str(safe[key]))
        return safe

    @staticmethod
    def _wants_human(message: str) -> bool:
        folded = message.casefold()
        return any(term in folded for term in ("humano", "atendente", "vendedor", "corretor", "me liga"))

    @staticmethod
    def _unsupported_media(message: str, message_type: str = "text") -> bool:
        if message_type in {"audio", "image", "document"}:
            return True
        folded = message.casefold()
        return any(marker in folded for marker in ("[audio]", "[documento]", "[imagem]"))

    def _handoff(self, state: ConversationState, reason: str) -> str:
        state.status = AgentStatus.HANDOFF
        state.handoff_reason = reason
        folded = reason.casefold()
        if "estimativa" in folded:
            return (
                "Tentei consultar o sistema de cotacao e gerei apenas uma estimativa preliminar. "
                "Ela nao e cotacao oficial, entao vou encaminhar seu atendimento para um especialista validar os dados e confirmar o valor com seguranca."
            )
        if "indisponivel" in folded or "legado" in folded:
            return (
                "Tentei consultar o sistema de cotacao, mas ele ficou indisponivel depois das tentativas automaticas. "
                "Para nao te passar um valor inseguro, vou encaminhar seu atendimento para um especialista com todos os dados ja coletados."
            )
        if "recusada" in folded:
            return (
                "A regra da cotacao recusou esse perfil automaticamente. "
                "Vou encaminhar para um especialista explicar o criterio e avaliar alternativas permitidas."
            )
        if "midia" in folded:
            return (
                "Recebi o anexo, mas neste canal eu ainda nao consigo analisar midia com seguranca. "
                "Vou encaminhar para um especialista revisar o material e continuar o atendimento."
            )
        if "aceitou" in folded or "emissao" in folded:
            return (
                "Perfeito. Vou encaminhar para um especialista finalizar a emissao com voce e confirmar os dados obrigatorios antes da proposta."
            )
        if "recusou" in folded:
            return (
                "Sem problema. Vou registrar a decisao e encaminhar para um especialista avaliar se existe alguma alternativa melhor para o seu caso."
            )
        return (
            "Vou encaminhar para um especialista humano com o contexto que ja coletei. "
            f"Motivo: {reason}. Assim evitamos travar seu atendimento ou passar uma cotacao insegura."
        )

    @staticmethod
    def _next_question(state: ConversationState, missing: list[str]) -> str:
        first = missing[0]
        prefix = "Perfeito, ja anotei o que consegui. "
        if first == "idade":
            return prefix + "Para calcular corretamente, preciso so de mais um dado: qual e a idade do principal condutor?"
        if first == "ano do veiculo":
            return prefix + "Qual e o modelo e ano do veiculo? Pode mandar como: Corolla 2020."
        if first == "CEP":
            return prefix + "Qual e o CEP onde o carro costuma dormir?"
        if first == "plano":
            return (
                prefix
                + "Voce prefere Essencial, Completo ou Premium? Se nao souber, posso seguir com o Completo como recomendacao equilibrada."
            )
        return prefix + f"Falta so: {first}."

    @staticmethod
    def _safe_llm_reply_draft(reply: str | None) -> str | None:
        if not reply:
            return None
        folded = reply.casefold()
        blocked_markers = ("r$", "premio_mensal", "prêmio mensal", "franquia:", "desconto")
        if any(marker in folded for marker in blocked_markers):
            return None
        redacted = redact_text(reply)
        return redacted[:600] if redacted else None

    @staticmethod
    def _quote_success_reply(result: QuoteResult) -> str:
        quote = result.quote or {}
        carencia = quote.get("carencia") or {}
        pro_rata = quote.get("primeiro_pagamento_pro_rata")
        parts = [
            f"Consegui cotar o plano {quote.get('plano_nome')} por R$ {quote.get('premio_mensal'):.2f}/mes.",
            f"Franquia: R$ {quote.get('franquia')}.",
            "Coberturas: " + ", ".join(quote.get("coberturas") or []),
        ]
        if carencia.get("coberturas"):
            parts.append(
                f"Roubo/furto tem carencia de {carencia.get('dias')} dias, conforme regra do plano."
            )
        if pro_rata:
            parts.append(
                "Como a vigencia comeca no meio do mes, o primeiro pagamento fica proporcional: "
                f"R$ {pro_rata.get('valor_primeiro_pagamento')}."
            )
        parts.append("Quer seguir com esse plano ou prefere falar com um especialista?")
        return " ".join(parts)

    def _after_quote_reply(self, state: ConversationState, message: str) -> str:
        folded = message.casefold()
        if any(
            term in folded
            for term in (
                "fechado",
                "pode emitir",
                "vamos nessa",
                "gostei",
                "quero seguir",
                "pode seguir",
            )
        ):
            return self._handoff(state, "lead aceitou cotacao e precisa emissao humana")
        if any(
            term in folded
            for term in (
                "vou ficar com a outra",
                "deixa pra la",
                "deixa pra lá",
                "nao precisa",
                "não precisa",
                "sem interesse",
                "vou fechar com outra",
            )
        ):
            return self._handoff(state, "lead recusou proposta apos cotacao")
        if any(term in folded for term in ("caro", "franquia alta", "concorrente", "desconto")):
            return self._handoff(state, "lead trouxe negociacao ou objecao comercial apos cotacao")
        return (
            "A cotacao ja esta pronta acima. Posso encaminhar para emissao ou chamar um "
            "especialista para revisar com voce."
        )
