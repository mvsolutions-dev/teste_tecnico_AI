from app.llm.factory import build_llm_provider


LLM_ENVS = [
    "AUTOSEGURO_LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_DEPLOYMENT_MINI",
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_MODEL",
    "AZURE_FOUNDRY_API_KEY",
    "AZURE_FOUNDRY_ENDPOINT",
    "AZURE_FOUNDRY_DEPLOYMENT",
]


def _clear_env(monkeypatch) -> None:  # noqa: ANN001
    for key in LLM_ENVS:
        monkeypatch.delenv(key, raising=False)


def test_factory_disabled_returns_disabled(monkeypatch) -> None:  # noqa: ANN001
    _clear_env(monkeypatch)

    provider = build_llm_provider("disabled")

    assert provider.name == "disabled"


def test_factory_auto_without_env_returns_disabled(monkeypatch) -> None:  # noqa: ANN001
    _clear_env(monkeypatch)

    provider = build_llm_provider("auto")

    assert provider.name == "disabled"


def test_factory_auto_with_openai_env_returns_openai(monkeypatch) -> None:  # noqa: ANN001
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    provider = build_llm_provider("auto")

    assert provider.name == "openai"
    assert provider.model == "gpt-test"


def test_factory_auto_prefers_compatible_over_azure(monkeypatch) -> None:  # noqa: ANN001
    _clear_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "azure-model")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "compatible-model")

    provider = build_llm_provider("auto")

    assert provider.name == "openai_compatible"
    assert provider.model == "compatible-model"
