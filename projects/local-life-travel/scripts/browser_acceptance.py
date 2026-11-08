"""Real headless Chrome acceptance: fixture selection, submit, poll, and revision.

Requires Playwright. Run with webapp-testing/with_server.py and a temporary DB.
Artifacts preserve browser evidence separately from pytest and live suppliers.
"""
from pathlib import Path
import argparse
import json
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--output', default='evidence/browser')
args = parser.parse_args()
output = Path(args.output).resolve()
output.mkdir(parents=True, exist_ok=True)
cases = [
    ('F01', 'completed', 'verified_feasible'),
    ('F05', 'completed', 'verified_feasible'),
    ('F09', 'completed', 'infeasible'),
    ('F11', 'needs_input', 'unverified'),
    ('F14', 'completed', 'partially_verified'),
    ('F16', 'failed', 'unverified'),
]
report = {'scope': 'real headless Chrome, local replay only', 'cases': [], 'page_errors': []}
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='chrome', headless=True)
    report['browser_version'] = browser.version
    context = browser.new_context(viewport={'width': 1400, 'height': 1000})
    page = context.new_page()
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    for scenario, expected_status, expected_quality in cases:
        page.goto('http://127.0.0.1:8765/', wait_until='networkidle')
        expect(page.locator('#scenario option')).to_have_count(20)
        page.locator('#scenario').select_option(scenario)
        page.locator('#load').click()
        expect(page.locator('#formMsg')).to_contain_text(f'已载入 {scenario}')
        with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/api/v1/travel/runs')) as submitted:
            page.locator('#submit').click()
        response = submitted.value
        assert response.status == 202, response.text()
        created = response.json()
        run_id = created['run_id']
        page.locator('#result .st-completed, #result .st-failed, #result .st-needs_input, #result .st-cancelled').wait_for(timeout=15000)
        final = context.request.get(f'http://127.0.0.1:8765/api/v1/travel/runs/{run_id}').json()
        row = {'scenario': scenario, 'run_id': run_id,
               'status': final['status'], 'quality': final['quality_status'],
               'expected_status': expected_status, 'expected_quality': expected_quality,
               'passed': final['status'] == expected_status and final['quality_status'] == expected_quality}
        if row['passed']:
            expect(page.locator(f'#result .st-{expected_status}')).to_be_visible()
            if expected_quality:
                expect(page.locator(f'#result .q-{expected_quality}')).to_be_visible()
        page.screenshot(path=str(output / f'{scenario}.png'), full_page=True)
        (output / f'{scenario}.json').write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding='utf-8')
        if scenario == 'F11':
            page.locator('input[type=radio]').first.check()
            with page.expect_response(lambda r: r.request.method == 'POST' and r.url.endswith('/revisions')) as revised:
                page.locator('#revisionBtn').click()
            child = revised.value.json()
            assert revised.value.status == 202, child
            page.locator('#result .st-completed').wait_for(timeout=15000)
            expect(page.locator('#result')).to_contain_text(child['run_id'])
            child_final = context.request.get(f'http://127.0.0.1:8765/api/v1/travel/runs/{child["run_id"]}').json()
            parent = context.request.get(f'http://127.0.0.1:8765/api/v1/travel/runs/{run_id}').json()
            row['revision_passed'] = (child_final['parent_run_id'] == run_id and child_final['revision'] == 2
                                      and parent['status'] == 'needs_input' and child_final['status'] == 'completed')
            row['passed'] = row['passed'] and row['revision_passed']
            page.screenshot(path=str(output / 'F11-revision.png'), full_page=True)
        report['cases'].append(row)
    context.close()
    browser.close()
report['passed'] = all(row['passed'] for row in report['cases']) and not report['page_errors']
(output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if report['passed'] else 1)
