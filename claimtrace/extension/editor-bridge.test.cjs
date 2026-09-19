const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const bridge = fs.readFileSync(path.join(__dirname, 'src/editor-bridge.js'), 'utf8');

function readDocument(elements) {
  const listeners = {};
  let response;
  const document = {
    querySelectorAll: selector => elements[selector] || [],
    addEventListener: (name, fn) => { listeners[name] = fn; },
    dispatchEvent: event => { response = JSON.parse(event.detail); },
  };
  vm.runInNewContext(bridge, { document, CustomEvent: class {
    constructor(type, init) { this.type = type; this.detail = init.detail; }
  } });
  listeners['claimtrace:read-editor']();
  return response.text;
}

test('CodeMirror reads the full document, not truncated or scrolled viewport text', () => {
  const full = '@article{one,title={One}}\n@article{two,title={Two}}';
  const element = { textContent: '@article{one,title={', cmView: { rootView: { view: { state: { doc: { toString: () => full } } } } } };
  assert.equal(readDocument({ '.cm-content': [element] }), full);
  element.textContent = 'title={Two}}';
  assert.equal(readDocument({ '.cm-content': [element] }), full);
});

test('missing or changed editor API fails closed instead of returning a partial Bib', () => {
  assert.equal(readDocument({ '.cm-content': [{ textContent: '@article{partial}' }] }), null);
  const broken = { get cmView() { throw new Error('Editor detached'); } };
  assert.equal(readDocument({ '.cm-content': [broken] }), null);
});

test('Ace reads the full editor session', () => {
  assert.equal(readDocument({ '.ace_editor': [{ env: { editor: { getValue: () => 'full Ace source' } } }] }), 'full Ace source');
});
