import pytest

from pet_sitting_palantir.lambda_handler import lambda_handler


class FakeDueResult:
    def __init__(self, *, scopes_due: int = 1, scopes_failed: int = 0) -> None:
        self.scopes_due = scopes_due
        self.scopes_failed = scopes_failed

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "success" if self.scopes_failed == 0 else "failed",
            "scopes_due": self.scopes_due,
            "scopes_succeeded": self.scopes_due - self.scopes_failed,
            "scopes_failed": self.scopes_failed,
            "results": [],
            "failures": [],
        }


def test_lambda_handler_imports_and_runs_due_scopes_with_all_pages(monkeypatch) -> None:
    captured_max_pages = []

    def fake_run_due_scrape_scopes(*, max_pages):
        captured_max_pages.append(max_pages)
        return FakeDueResult(scopes_due=1, scopes_failed=0)

    monkeypatch.setattr(
        "pet_sitting_palantir.lambda_handler.run_due_scrape_scopes",
        fake_run_due_scrape_scopes,
    )

    response = lambda_handler({"source": "aws.scheduler"}, object())

    assert captured_max_pages == [None]
    assert response["statusCode"] == 200
    assert response["body"]["status"] == "success"


def test_lambda_handler_raises_when_due_scopes_fail(monkeypatch) -> None:
    captured_max_pages = []

    def fake_run_due_scrape_scopes(*, max_pages):
        captured_max_pages.append(max_pages)
        return FakeDueResult(scopes_due=2, scopes_failed=1)

    monkeypatch.setattr(
        "pet_sitting_palantir.lambda_handler.run_due_scrape_scopes",
        fake_run_due_scrape_scopes,
    )

    with pytest.raises(RuntimeError, match="failed for 1 of 2 scopes"):
        lambda_handler({}, object())

    assert captured_max_pages == [None]
