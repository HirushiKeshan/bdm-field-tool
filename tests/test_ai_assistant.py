"""No real network calls here -- the Groq client is mocked. What matters
for this module is that it never crashes the page, never calls the API
without a key, and always sends the grounding instruction plus the raw
data alongside the question -- not that a real model returns a good
answer, which is a live-testing concern, not a unit-testing one."""
from unittest.mock import MagicMock, patch

from logic import ai_assistant


def test_missing_api_key_returns_a_clear_message_and_makes_no_network_call():
    with patch.object(ai_assistant, "get_api_key", return_value=None), \
         patch("logic.ai_assistant.Groq") as mock_groq:
        result = ai_assistant.ask("Which BDM needs help?", {"some": "data"})
    assert "GROQ_API_KEY" in result
    mock_groq.assert_not_called()


def test_ask_sends_the_grounding_instruction_and_the_raw_data():
    fake_response = MagicMock()
    fake_response.choices[0].message.content = "  Praveen K, at 22%.  "
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = fake_response

    with patch.object(ai_assistant, "get_api_key", return_value="fake-key"), \
         patch("logic.ai_assistant.Groq", return_value=mock_client):
        result = ai_assistant.ask("Which BDM needs help?", {"time_allocation_by_bdm": [{"bdm": "Praveen K"}]})

    assert result == "Praveen K, at 22%."  # stripped, not just passed through
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == ai_assistant.MODEL
    assert call_kwargs["temperature"] <= 0.2  # low temperature -- this isn't creative writing
    messages = call_kwargs["messages"]
    assert any("never invent" in m["content"].lower() for m in messages if m["role"] == "system")
    assert any("Praveen K" in m["content"] for m in messages if m["role"] == "system")
    assert messages[-1] == {"role": "user", "content": "Which BDM needs help?"}


def test_api_failure_returns_a_message_instead_of_raising():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("rate limited")

    with patch.object(ai_assistant, "get_api_key", return_value="fake-key"), \
         patch("logic.ai_assistant.Groq", return_value=mock_client):
        result = ai_assistant.ask("Anything?", {})

    assert "rate limited" in result
    assert "unaffected" in result
