import pytest
from app.assistant import Intent, interpret_ai


def test_missing_key_does_not_change_rules_or_claim_ai(client, monkeypatch):
    monkeypatch.delenv("RG_AI_API_KEY", raising=False)
    before = client.get("/api/rules").json()
    assert client.get("/api/assistant/status").json()["configured"] is False
    r = client.post("/api/assistant/ai", json={"command": "approve all transfers"})
    assert r.status_code == 422 and "RG_AI_API_KEY" in r.text
    assert client.get("/api/rules").json() == before


def test_ai_schema_rejects_execution_actions():
    with pytest.raises(ValueError):
        Intent(view="dispatch", branch="NV", material="gold", explanation="Done")


def test_ai_request_uses_structured_output_and_no_execution_tools(monkeypatch):
    import asyncio

    seen = {}

    class Responses:
        async def parse(self, **kwargs):
            seen.update(kwargs)
            return type(
                "Result",
                (),
                {
                    "output_parsed": Intent(
                        view="ageing",
                        branch="NV",
                        material="gold",
                        explanation="Ageing is based on original label dates.",
                    )
                },
            )()

    class Client:
        def __init__(self, **kwargs):
            self.responses = Responses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setenv("RG_AI_API_KEY", "test-placeholder")
    monkeypatch.setattr("app.assistant.AsyncOpenAI", Client)
    result = asyncio.run(
        interpret_ai(
            "show old gold at NV",
            {"provenance": {"snapshot_id": 1, "rule_id": 2}, "branch_health": []},
        )
    )
    assert result["provenance"]["snapshot_id"] == 1
    assert result["view"] == "ageing"
    assert seen["text_format"] is Intent
    assert "tools" not in seen
    assert "test-placeholder" not in str(seen)
