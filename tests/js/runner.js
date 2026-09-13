export const results = [];
let currentSuite = '(no suite)';

export function suite(name) {
  currentSuite = name;
}

export function test(name, fn) {
  try {
    fn();
    results.push({ suite: currentSuite, name, ok: true });
  } catch (err) {
    results.push({ suite: currentSuite, name, ok: false, err: err.message });
  }
}

export function assertEq(actual, expected, msg) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${msg || 'assertEq'}: expected ${e}, got ${a}`);
}

export function assertApprox(actual, expected, epsilon, msg) {
  if (typeof actual !== 'number' || isNaN(actual)) throw new Error(`${msg || 'assertApprox'}: actual is not a number (${actual})`);
  if (Math.abs(actual - expected) > epsilon) throw new Error(`${msg || 'assertApprox'}: expected ~${expected} (±${epsilon}), got ${actual}`);
}

export function assertTrue(cond, msg) {
  if (!cond) throw new Error(msg || 'assertTrue failed');
}

export function render() {
  const root = document.getElementById('results');
  let pass = 0;
  for (const r of results) {
    if (r.ok) pass++;
    const div = document.createElement('div');
    div.textContent = `${r.ok ? '✓' : '✗'} [${r.suite}] ${r.name}${r.err ? ` — ${r.err}` : ''}`;
    div.style.color = r.ok ? '#0a7' : '#c00';
    div.style.fontFamily = 'monospace';
    root.appendChild(div);
  }
  const summary = document.createElement('div');
  summary.textContent = `${pass}/${results.length} passed`;
  summary.style.fontWeight = 'bold';
  summary.style.marginTop = '1em';
  summary.style.fontFamily = 'monospace';
  root.appendChild(summary);
}
