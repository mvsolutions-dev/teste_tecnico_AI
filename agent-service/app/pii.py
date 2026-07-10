from __future__ import annotations

import re


CPF_RE = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b")
PHONE_RE = re.compile(r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?9?\d{4}[-\s]?\d{4}")
PLATE_RE = re.compile(r"\b[A-Z]{3}\d[A-Z0-9]\d{2}\b", re.IGNORECASE)


def mask_cpf(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) != 11:
        return "***"
    return f"***.{digits[3:6]}.{digits[6:9]}-**"


def mask_email(value: str) -> str:
    user, _, domain = value.partition("@")
    if not user or not domain:
        return "***"
    return f"{user[:2]}***@{domain}"


def mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 8:
        return "***"
    return f"***{digits[-4:]}"


def redact_text(text: str) -> str:
    text = CPF_RE.sub(lambda m: mask_cpf(m.group(0)), text)
    text = EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
    text = PHONE_RE.sub(lambda m: mask_phone(m.group(0)), text)
    text = PLATE_RE.sub("***PLACA***", text)
    return text

