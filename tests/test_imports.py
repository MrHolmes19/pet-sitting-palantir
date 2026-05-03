from pet_sitting_palantir.config import load_settings
from pet_sitting_palantir.main import main


def test_main_returns_success(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "pet_sitting_palantir.main.scrape_scope",
        lambda site_filter, max_pages: type(
            "Result",
            (),
            {"search_url": "https://example.test/search", "pages_fetched": 0, "listings": []},
        )(),
    )
    monkeypatch.setattr("sys.argv", ["pet-sitting-palantir"])

    assert main() == 0
    assert '"listings_seen": 0' in capsys.readouterr().out


def test_settings_load_from_clean_environment(monkeypatch) -> None:
    for name in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "DATABASE_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = load_settings()

    assert settings.supabase_url is None
    assert settings.supabase_service_role_key is None
    assert settings.database_url is None
    assert settings.telegram_bot_token is None
    assert settings.telegram_chat_id is None
