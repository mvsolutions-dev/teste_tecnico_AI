from app.extraction import LeadExtractor


def test_extracts_quote_slots_and_masks_pii() -> None:
    extractor = LeadExtractor(use_llm=False)

    result = extractor.extract(
        "Tenho 35 anos, CPF 389.083.863-43, CEP 26703-384. "
        "Meu carro e um Corolla 2022 e quero completo."
    )

    assert result.updates["idade"] == 35
    assert result.updates["cep"] == "26703-384"
    assert result.updates["veiculo_ano"] == 2022
    assert result.updates["plano_id"] == "completo"
    assert result.updates["cpf_masked"] == "***.083.863-**"


def test_delegated_plan_defaults_to_completo() -> None:
    extractor = LeadExtractor(use_llm=False)

    result = extractor.extract("Nao sei qual plano, voce escolhe pra mim.")

    assert result.updates["plano_id"] == "completo"
    assert "observacoes" in result.updates


def test_vehicle_year_ignores_policy_start_date() -> None:
    extractor = LeadExtractor(use_llm=False)

    result = extractor.extract(
        "Sou Ana, tenho 35 anos, CPF 389.083.863-43, CEP 01310-100. "
        "Meu carro e um Corolla 2022 e quero completo com inicio em 15/07/2026."
    )

    assert result.updates["nome"] == "Ana"
    assert result.updates["veiculo_ano"] == 2022
    assert "Corolla 2022" in result.updates["veiculo_texto"]
    assert result.updates["data_inicio"] == "2026-07-15"


def test_vehicle_text_does_not_include_plan_intent() -> None:
    extractor = LeadExtractor(use_llm=False)

    result = extractor.extract(
        "Me chamo Carlos Eduardo. Meu carro e um Honda Civic de 2021 e queria o premium."
    )

    assert result.updates["veiculo_texto"] == "Honda Civic 2021"
    assert result.updates["veiculo_marca"] == "Honda"
    assert result.updates["veiculo_modelo"] == "Civic"
    assert result.updates["plano_id"] == "premium"


def test_llm_fallback_is_visible_without_breaking_extraction(monkeypatch) -> None:
    extractor = LeadExtractor(use_llm=True)

    def fake_llm_extract(message, current, deterministic):  # noqa: ANN001
        return {}, "RateLimitError"

    monkeypatch.setattr(extractor, "_llm_extract", fake_llm_extract)

    result = extractor.extract("Tenho 35 anos, CEP 01310-100, Corolla 2022")

    assert result.source == "deterministic+llm_fallback"
    assert result.llm_error_type == "RateLimitError"
    assert result.updates["idade"] == 35


def test_vehicle_text_is_normalized_from_noisy_lead_message() -> None:
    extractor = LeadExtractor(use_llm=False)

    result = extractor.extract(
        "Sou Ana, tenho 35 anos, CEP 01310-100. Meu carro é um Corolla 2022 e quero completo."
    )

    assert result.updates["veiculo_texto"] == "Toyota Corolla 2022"
    assert result.updates["veiculo_marca"] == "Toyota"
    assert result.updates["veiculo_modelo"] == "Corolla"


def test_vehicle_text_supports_common_models_without_pii() -> None:
    extractor = LeadExtractor(use_llm=False)

    cases = {
        "Tenho 41 anos, CEP 01310-100, carro T-Cross 2021, quero premium.": "Volkswagen T-Cross 2021",
        "Meu veículo é um Honda Civic 2020, tenho 29 anos.": "Honda Civic 2020",
        "Tenho um HB20 2023, CPF 389.083.863-43, placa ABC1D23.": "Hyundai HB20 2023",
    }

    for message, expected in cases.items():
        result = extractor.extract(message)
        assert result.updates["veiculo_texto"] == expected
        assert "389" not in result.updates["veiculo_texto"]
        assert "ABC" not in result.updates["veiculo_texto"]


def test_unknown_vehicle_fallback_does_not_turn_ano_into_model() -> None:
    extractor = LeadExtractor(use_llm=False)

    result = extractor.extract("Tenho 55 anos, CEP 04623-171, veiculo Pulse, ano 2008.")

    assert result.updates["veiculo_texto"] == "Pulse 2008"
    assert result.updates["veiculo_modelo"] == "Pulse"
    assert "veiculo_marca" not in result.updates
