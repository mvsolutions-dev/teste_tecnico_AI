from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path) -> bool:
    """Carrega um .env simples sem adicionar dependencia externa.

    Valores ja definidos no ambiente vencem o arquivo. A funcao nao imprime
    secrets e ignora linhas sem `=`.
    """
    env_path = Path(path)
    if not env_path.exists():
        return False
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    return True


def load_default_env() -> list[str]:
    """Tenta carregar .env do cwd e do agent-service.

    Retorna apenas os caminhos carregados, sem valores. Isso permite usar uma
    chave local para testes sem acoplar o codigo ao ambiente do avaliador.
    """
    loaded: list[str] = []
    candidates = []
    explicit = os.getenv("AUTOSEGURO_ENV_FILE")
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[1] / ".env",
        ]
    )
    for candidate in candidates:
        if load_env_file(candidate):
            loaded.append(str(candidate))
    return loaded
