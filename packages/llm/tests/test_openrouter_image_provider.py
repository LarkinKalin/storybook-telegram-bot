import pytest

from packages.llm.src import openrouter_image_provider


def test_image_provider_sim_fail_always_raises(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("SKAZKA_IMAGE_PROVIDER_SIM_FAIL", "1")

    with pytest.raises(RuntimeError, match="simulated image provider failure"):
        openrouter_image_provider.generate_t2i("scene one")

    with pytest.raises(RuntimeError, match="simulated image provider failure"):
        openrouter_image_provider.generate_t2i("scene two")
