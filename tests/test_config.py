import pytest
from pydantic import ValidationError

from improv_troupe.config import AppConfig, BackendConfig, ServiceSettings


def test_backend_timeout_defaults_to_five_minutes():
    config = AppConfig.model_validate(
        {"backends": {"local": {"base_url": "http://127.0.0.1:11434/v1"}}}
    )

    assert config.backend("local").timeout_seconds == 300


def test_backend_timeout_is_configurable_and_bounded():
    backend = BackendConfig(
        base_url="http://127.0.0.1:11434/v1",
        timeout_seconds=420,
    )

    assert backend.timeout_seconds == 420
    with pytest.raises(ValidationError):
        BackendConfig(base_url="http://127.0.0.1:11434/v1", timeout_seconds=0)
    with pytest.raises(ValidationError):
        BackendConfig(base_url="http://127.0.0.1:11434/v1", timeout_seconds=1801)


def test_recovery_wait_defaults_to_four_hours_and_can_be_disabled():
    assert ServiceSettings().recovery_wait_seconds == 14_400
    assert ServiceSettings(recovery_wait_seconds=0).recovery_wait_seconds == 0

    with pytest.raises(ValidationError):
        ServiceSettings(recovery_wait_seconds=-1)
