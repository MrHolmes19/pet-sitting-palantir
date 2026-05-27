from pet_sitting_palantir.config import load_settings
from pet_sitting_palantir.main import main
from pet_sitting_palantir.workflows.deliver_alerts import AlertDeliverySummary
from pet_sitting_palantir.workflows.home_runner import RunnerAlreadyActiveError


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


def test_main_supports_summary_output(monkeypatch, capsys) -> None:
    class FakeListing:
        def to_dict(self) -> dict[str, object]:
            return {
                "external_id": "614587",
                "content_hash": "hash",
                "island": "North Island",
                "region": "Auckland",
                "subregion": "Auckland - Central",
                "city": "Stonefields",
                "duration_days": 16,
                "start_date": "2026-06-12",
                "end_date": "2026-06-28",
                "house_type": "House",
                "total_animals": 1,
                "dogs_count": 1,
                "cats_count": 0,
                "fish_count": 0,
                "birds_count": 0,
                "rabbits_guinea_pigs_count": 0,
                "chickens_ducks_geese_count": 0,
                "farm_animals_count": 0,
                "horses_count": 0,
                "reptiles_count": 0,
                "other_pets_count": 0,
                "no_pets": False,
                "starts_soon": True,
                "reply_rating_score": 10,
                "listing_tag": "Goofy Dog in Stonefields",
                "title": "Stonefields Auckland - Auckland - Auckland - Central",
                "intro": "Looking for someone to look after one dog.",
                "url": "https://example.test/listing",
            }

    monkeypatch.setattr(
        "pet_sitting_palantir.main.scrape_scope",
        lambda site_filter, max_pages: type(
            "Result",
            (),
            {
                "search_url": "https://example.test/search",
                "pages_fetched": 1,
                "listings": (FakeListing(),),
            },
        )(),
    )
    monkeypatch.setattr("sys.argv", ["pet-sitting-palantir", "--summary"])

    assert main() == 0
    output = capsys.readouterr().out
    assert '"external_id": "614587"' in output
    assert '"content_hash"' not in output
    assert '"intro"' not in output


def test_main_supports_persist_output(monkeypatch, capsys) -> None:
    class FakeStoredResult:
        def to_dict(self) -> dict[str, object]:
            return {
                "scope_name": "auckland_central",
                "run_id": 123,
                "search_url": "https://example.test/search",
                "pages_fetched": 1,
                "listings_seen": 2,
                "new_listings": 1,
                "changed_listings": 1,
                "missing_marked": 0,
                "status": "success",
            }

    monkeypatch.setattr(
        "pet_sitting_palantir.main.scrape_and_store_scope",
        lambda scope_name, max_pages: FakeStoredResult(),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["pet-sitting-palantir", "--scope", "auckland_central", "--max-pages", "1", "--persist"],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert '"scope_name": "auckland_central"' in output
    assert '"run_id": 123' in output
    assert '"status": "success"' in output


def test_main_supports_run_due_output(monkeypatch, capsys) -> None:
    class FakeDueResult:
        scopes_failed = 0

        def to_dict(self) -> dict[str, object]:
            return {
                "status": "success",
                "scopes_due": 1,
                "scopes_succeeded": 1,
                "scopes_failed": 0,
                "results": [],
                "failures": [],
            }

    monkeypatch.setattr(
        "pet_sitting_palantir.main.run_due_scrape_scopes",
        lambda max_pages: FakeDueResult(),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["pet-sitting-palantir", "--run-due", "--max-pages", "1"],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert '"status": "success"' in output
    assert '"scopes_due": 1' in output


def test_main_supports_all_pages(monkeypatch, capsys) -> None:
    class FakeDueResult:
        scopes_failed = 0

        def to_dict(self) -> dict[str, object]:
            return {
                "status": "nothing_due",
                "scopes_due": 0,
                "scopes_succeeded": 0,
                "scopes_failed": 0,
                "results": [],
                "failures": [],
            }

    captured_max_pages = []

    def fake_run_due_scrape_scopes(max_pages):
        captured_max_pages.append(max_pages)
        return FakeDueResult()

    monkeypatch.setattr(
        "pet_sitting_palantir.main.run_due_scrape_scopes",
        fake_run_due_scrape_scopes,
    )
    monkeypatch.setattr(
        "sys.argv",
        ["pet-sitting-palantir", "--run-due", "--max-pages", "all"],
    )

    assert main() == 0
    assert captured_max_pages == [None]
    assert '"status": "nothing_due"' in capsys.readouterr().out


def test_main_returns_failure_when_run_due_has_failures(monkeypatch, capsys) -> None:
    class FakeDueResult:
        scopes_failed = 1

        def to_dict(self) -> dict[str, object]:
            return {
                "status": "failed",
                "scopes_due": 1,
                "scopes_succeeded": 0,
                "scopes_failed": 1,
                "results": [],
                "failures": [{"scope_name": "auckland_central", "error_message": "boom"}],
            }

    monkeypatch.setattr(
        "pet_sitting_palantir.main.run_due_scrape_scopes",
        lambda max_pages: FakeDueResult(),
    )
    monkeypatch.setattr("sys.argv", ["pet-sitting-palantir", "--run-due"])

    assert main() == 1
    assert '"status": "failed"' in capsys.readouterr().out


def test_main_supports_continuous_home_runner_with_all_pages(monkeypatch) -> None:
    captured_max_pages = []

    monkeypatch.setattr(
        "pet_sitting_palantir.main.run_home_runner",
        lambda *, max_pages: captured_max_pages.append(max_pages),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["pet-sitting-palantir", "--run-continuously", "--max-pages", "all"],
    )

    assert main() == 0
    assert captured_max_pages == [None]


def test_main_supports_manual_alert_delivery(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "pet_sitting_palantir.main.deliver_due_alerts",
        lambda: AlertDeliverySummary(
            deliveries_due=1,
            attempts_made=1,
            sent=1,
            failed=0,
            unconfigured=0,
            failures=(),
        ),
    )
    monkeypatch.setattr("sys.argv", ["pet-sitting-palantir", "--deliver-alerts"])

    assert main() == 0
    assert '"sent": 1' in capsys.readouterr().out


def test_main_reports_an_already_active_continuous_runner(monkeypatch, capsys) -> None:
    def fail_to_acquire_lock(*, max_pages):
        raise RunnerAlreadyActiveError("Production runner is already active")

    monkeypatch.setattr(
        "pet_sitting_palantir.main.run_home_runner",
        fail_to_acquire_lock,
    )
    monkeypatch.setattr("sys.argv", ["pet-sitting-palantir", "--run-continuously"])

    assert main() == 1
    assert "Production runner is already active" in capsys.readouterr().err


def test_main_supports_init_db_output(monkeypatch, capsys) -> None:
    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class FakeInitResult:
        def to_dict(self) -> dict[str, object]:
            return {
                "schema_applied": True,
                "seed_applied": True,
            }

    monkeypatch.setattr("pet_sitting_palantir.main.connect_database", lambda: FakeConnection())
    monkeypatch.setattr(
        "pet_sitting_palantir.main.initialize_database",
        lambda connection: FakeInitResult(),
    )
    monkeypatch.setattr("sys.argv", ["pet-sitting-palantir", "--init-db"])

    assert main() == 0
    output = capsys.readouterr().out
    assert '"schema_applied": true' in output
    assert '"seed_applied": true' in output


def test_settings_load_from_clean_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
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


def test_settings_load_from_dotenv(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql://palantir:palantir@localhost:54321/pet_sitting_palantir\n"
    )

    settings = load_settings()

    assert (
        settings.database_url
        == "postgresql://palantir:palantir@localhost:54321/pet_sitting_palantir"
    )
