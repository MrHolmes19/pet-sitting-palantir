from pet_sitting_palantir.config import load_settings
from pet_sitting_palantir.main import main


def test_main_returns_success() -> None:
    assert main() == 0


def test_settings_load_from_environment() -> None:
    settings = load_settings()

    assert settings.supabase_url is None or isinstance(settings.supabase_url, str)
