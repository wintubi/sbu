// Executes the actual page JavaScript with a minimal DOM adapter.
// This verifies form data preservation; it is NOT a browser/E2E test.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const fixturePath = process.argv[2];
if (!fixturePath) throw new Error('Pass expanded /fixtures-shaped JSON as first argument');
const fixture = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
const defaults = { city: '杭州', date: '2026-11-08', timezone: 'Asia/Shanghai', offset: '+08:00',
  origin: '杭州东站', transport: 'transit', start: '09:00', end: '18:00',
  candidates: '西湖,7200\n灵隐寺,5400\n河坊街,3600' };
function element(id) {
  if (!elements.has(id)) elements.set(id, {value: defaults[id] || '', textContent: '',
    appendChild() {}, addEventListener() {}});
  return elements.get(id);
}
const context = vm.createContext({
  document: { getElementById: element, createElement: () => ({}) },
  fetch: async () => ({json: async () => fixture}),
  setTimeout, clearTimeout, console,
});
vm.runInContext(script, context, {filename: 'web/index.html'});
async function settle() { await new Promise(resolve => setImmediate(resolve)); }
const report = {scope: 'actual page JavaScript, minimal DOM adapter; not browser E2E', cases: []};
(async () => {
  await settle();
  for (const scenario of fixture.scenarios) {
    element('scenario').value = scenario.id;
    context.loadSelected();
    await settle();
    const actual = JSON.parse(JSON.stringify(context.buildRequest()));
    const expected = JSON.parse(JSON.stringify(scenario.request));
    const fields = ['mode','scenario_id','city','date','timezone','origin','time_window','transport',
      'candidates','preferences','manual_facts','selected_poi_ids'];
    const differing = fields.filter(key => {
      try { assert.deepStrictEqual(actual[key], expected[key]); return false; }
      catch { return true; }
    });
    report.cases.push({id: scenario.id, passed: !differing.length, differing});
  }
  report.edit_checks = [];
  async function load(id) { element('scenario').value = id; context.loadSelected(); await settle(); }
  await load('F09');
  element('candidates').value = element('candidates').value.replace('河坊街,3600', '河坊街,4200');
  let edited = JSON.parse(JSON.stringify(context.buildRequest()));
  const candidate = edited.candidates.find(c => c.name === '河坊街');
  report.edit_checks.push({name: 'duration edit preserves appointment', passed:
    candidate.stay_seconds === 4200 && candidate.optional_time_window?.start === '16:00'});
  await load('F05');
  element('scenario').value = 'F01';
  edited = JSON.parse(JSON.stringify(context.buildRequest()));
  report.edit_checks.push({name: 'unloaded different scenario does not inherit manual facts',
    passed: edited.manual_facts.length === 0});
  await load('F09');
  element('candidates').value = element('candidates').value.replace('河坊街,3600', '新地点,3600');
  edited = JSON.parse(JSON.stringify(context.buildRequest()));
  report.edit_checks.push({name: 'renamed candidate does not inherit another appointment',
    passed: !edited.candidates.find(c => c.name === '新地点').optional_time_window});
  report.passed = report.cases.every(item => item.passed) && report.edit_checks.every(item => item.passed);
  console.log(JSON.stringify(report, null, 2));
  if (!report.passed) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
