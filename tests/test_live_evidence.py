"""A mode label alone must never qualify an execution as strict live-model evidence."""
import pytest
from conftest import login
from test_pipeline import chat
from scripts.record_llm_demo import strict_checks


@pytest.mark.parametrize('reported_mode', ['demo', 'llm'])
def test_recording_rejects_demo_execution_even_with_an_llm_label(client, reported_mode):
    result = chat(client, login(client), 'I would like a refund for order O1002.')
    result['mode'] = reported_mode
    checks = strict_checks(result, 'refund')
    assert not checks['actual_model_calls']
    assert not checks['required_model_stages']
    assert not checks['semantic_queries']
    assert not checks['native_tool_execution']
    assert not checks['judge']
    assert not all(checks.values())
