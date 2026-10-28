"""Record actual LLM-backed UI journeys, with strict evidence and no fabricated responses.

Requires the existing browser extra, Chromium and a configured chat/embedding provider.
The WebM preserves real elapsed time, including inference waits. Both success and
failure reports retain the actual application responses.
"""
import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from atlas.config import Settings
from scripts.browser_demo import free_port, wait_healthy


def strict_checks(result, journey):
    roles = ({'orchestrator', 'returns_investigation', 'resolution'} if journey == 'refund' else
             {'orchestrator', 'order_tracking', 'product_discovery', 'personal_stylist'})
    stages = ({'Plan', 'returns_investigation', 'ResolutionDecision', 'AnswerSchema', 'JudgeVerdict'}
              if journey == 'refund' else
              {'Plan', 'order_tracking', 'product_discovery', 'OutfitDecision', 'AnswerSchema', 'JudgeVerdict'})
    actual_stages = {event['stage'] for event in result['model_usage']['events'] if event['ok']}
    checks = {
        'llm_mode':result['mode'] == 'llm',
        'actual_model_calls':result['model_usage']['calls'] > 0,
        'required_model_stages':stages <= actual_stages,
        'semantic_queries':result['embedding_usage']['calls'] > 0
            and result['embedding_usage']['model'] != 'lexical-hash-512-v1',
        'exact_roles':{trace['agent'] for trace in result['trace']} == roles,
        'native_tool_execution':all(next((t for t in result['trace'] if t['agent'] == role), {})
            .get('execution') == 'llm_tools' for role in roles &
            {'returns_investigation', 'order_tracking', 'product_discovery'}),
        'no_fallback':not result['degraded'] and not result['warnings'],
        'guardrails':result['guardrails']['passed'],
        'judge':result['judged'] and result['judge_evaluation']['passed'],
        'quality':result['quality']['passed'],
    }
    if journey == 'refund':
        action = result.get('action') or {}
        checks.update(amount_249=action.get('amount_cents') == 24900,
            awaiting_confirmation=action.get('status') == 'proposed' and not action.get('customer_confirmed'),
            required_human_review=action.get('requires_human') is True)
    else:
        trace = {t['agent']:t for t in result['trace']}
        outfit = result['outfit']
        checks.update(nonempty_outfit=bool(outfit),
            size_and_stock=all(p['size'] == 'M' and p['stock'] > 0 for p in outfit),
            total_budget=sum(p['price_cents'] for p in outfit) <= 15000,
            worker_overlap=bool(result['execution_summary']['parallel_pairs']),
            stylist_dependency=('personal_stylist' in trace and 'product_discovery' in trace and
                trace['personal_stylist']['started_ms'] >= trace['product_discovery']['ended_ms']),
            verified_tracking=any(f['agent'] == 'order_tracking' and f['evidence'].get('found') and
                f['evidence'].get('source') == 'live mock carrier API' for f in result['findings']))
    return checks


def run_journeys(page, base, key, report, output):
    page.on('pageerror', lambda error:report['javascript_errors'].append(str(error)))
    page.goto(base)
    page.get_by_text('Connected', exact=True).wait_for()
    report['health'] = page.evaluate("async () => (await fetch('/health')).json()")
    if report['health']['mode'] != 'llm' or report['health']['retrieval'] != 'semantic':
        raise RuntimeError('Recording requires real LLM mode and semantic retrieval')
    for journey, button in [('refund', 'Demo A · Refund & approval ↗'),
                            ('parallel', 'Demo B · Tracking & styling ↗')]:
        page.wait_for_timeout(1500)
        with page.expect_response(lambda response:response.url == base+'/api/chat'
                                  and response.request.method == 'POST', timeout=600000) as pending:
            page.get_by_role('button', name=button, exact=True).click()
        response = pending.value
        result = response.json()
        if response.status != 200:
            report['journeys'].append({'journey':journey, 'http_status':response.status, 'response':result})
            raise RuntimeError('Application chat failed during '+journey)
        checks = strict_checks(result, journey)
        report['journeys'].append({'journey':journey, 'request':response.request.post_data_json['message'],
                                  'checks':checks, 'result':result})
        page.wait_for_function("() => !busy")
        if not all(checks.values()):
            raise RuntimeError('Strict LLM checks failed: '+', '.join(k for k,v in checks.items() if not v))
        page.screenshot(path=str(output.with_suffix('.'+journey+'.png')), full_page=True)
        page.wait_for_timeout(2000)
        if journey == 'refund':
            page.get_by_role('button', name='Confirm refund proposal', exact=True).click()
            page.get_by_role('button', name='Confirmed · awaiting human review', exact=True).wait_for()
            page.wait_for_timeout(1500)
            page.locator('#opsTab').click()
            page.locator('#adminKey').fill(key)
            page.locator('#loadReviews').click()
            page.get_by_role('button', name='Approve simulation', exact=True).wait_for()
            page.get_by_placeholder('Decision reason (required)').fill('Verified fictional receipt and inspection')
            page.wait_for_timeout(1500)
            page.get_by_role('button', name='Approve simulation', exact=True).click()
            page.get_by_text('No requests awaiting review.', exact=True).wait_for()
            page.locator('#drain').click()
            page.get_by_text('1 simulated payment(s) completed. No real money moved.', exact=True).wait_for()
            page.wait_for_function("document.querySelector('#audit').textContent.includes('completed_simulation')")
            report['refund_audit'] = json.loads(page.locator('#audit').text_content())
            events = [row['event'] for row in report['refund_audit']]
            checks['confirmation_approval_and_simulation'] = (
                'confirmed' in events and any(event.startswith('approved:') for event in events)
                and events[-1] == 'completed_simulation')
            page.wait_for_timeout(1500)
            page.locator('#customerTab').click()
            page.get_by_role('button', name='Completed · simulated payment', exact=True).wait_for()
        else:
            page.locator('.trace summary').first.click()
            page.locator('#trace').scroll_into_view_if_needed()
            page.wait_for_timeout(2500)


def record(output):
    from playwright.sync_api import sync_playwright
    config = Settings(atlas_mode='llm')
    config.validate_runtime()
    if not config.embedding_model:
        raise ValueError('Set EMBEDDING_MODEL; lexical retrieval cannot qualify as a real-LLM recording')
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    sources = [*Path('atlas').glob('*.py'), *Path('atlas/static').glob('*'), Path(__file__)]
    report = {'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'mode':'llm',
        'recording':'Actual browser execution at original speed; inference waits are included.',
        'model':config.openai_model, 'embedding_model':config.embedding_model,
        'source_sha256':{str(p.resolve().relative_to(Path.cwd())):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sources}, 'journeys':[], 'javascript_errors':[]}
    provider_env = {name.upper():json.dumps(value) if isinstance(value, dict) else str(value)
                    for name,value in config.model_dump().items() if value is not None}
    key = secrets.token_urlsafe(24)
    api_port, carrier_port = free_port(), free_port()
    base = f'http://127.0.0.1:{api_port}'
    processes = []
    with tempfile.TemporaryDirectory(prefix='atlas-live-ui-') as tmp:
        env = {**os.environ, **provider_env, 'ATLAS_MODE':'llm',
            'DATABASE_URL':'sqlite:///'+tmp+'/demo.db', 'CHROMA_PATH':tmp+'/chroma',
            'DATA_DIR':str(Path('data').resolve()), 'ADMIN_API_KEY':key, 'DEMO_ACCESS':'true',
            'CARRIER_BASE_URL':f'http://127.0.0.1:{carrier_port}', 'CARRIER_API_KEY':'',
            'AS_OF_DATE':'2026-10-26', 'NO_PROXY':os.environ.get('NO_PROXY', '')+',127.0.0.1,localhost'}
        with output.with_suffix('.server.log').open('w') as logfile:
            try:
                for module,port in [('atlas.mock_carrier:app', carrier_port), ('atlas.api:app', api_port)]:
                    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', module, '--host',
                        '127.0.0.1', '--port', str(port)], env=env, cwd=tmp, stdout=logfile, stderr=logfile)
                    processes.append(process)
                    wait_healthy(f'http://127.0.0.1:{port}', process)
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    context = browser.new_context(viewport={'width':1440, 'height':1100},
                        record_video_dir=tmp+'/video', record_video_size={'width':1440, 'height':1100})
                    page = context.new_page()
                    page.set_default_timeout(600000)
                    try:
                        run_journeys(page, base, key, report, output)
                    finally:
                        context.close()
                        page.video.save_as(str(output.with_suffix('.webm')))
                        browser.close()
            except Exception as exc:
                report['failure'] = type(exc).__name__+': '+str(exc)
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    video = output.with_suffix('.webm')
    if video.exists():
        report['video'] = {'file':video.name, 'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
                           'bytes':video.stat().st_size, 'playback_speed':1}
    report['passed'] = (not report.get('failure') and not report['javascript_errors']
        and len(report['journeys']) == 2 and all(all(row['checks'].values()) for row in report['journeys']))
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in {'source_sha256', 'journeys', 'refund_audit'}}, indent=2))
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='reports/llm-recording.json')
    args = parser.parse_args()
    raise SystemExit(0 if record(args.output) else 1)
