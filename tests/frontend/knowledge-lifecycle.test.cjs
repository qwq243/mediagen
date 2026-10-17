const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness(fetch) {
  const source = fs.readFileSync(path.join(__dirname, '../../scripts/static/ppt-workbench/knowledge.js'), 'utf8');
  const sandbox = {
    fetch, AbortController, DOMException, Map, setTimeout, clearTimeout,
    document: {querySelector: () => null},
    window: {addEventListener() {}, dispatchEvent() {}},
  };
  vm.createContext(sandbox);
  // Capture the actual private helper without exposing a production test API.
  vm.runInContext(source.replace('window.PPTKnowledge={', 'window.testApi=api;window.PPTKnowledge={'), sandbox);
  return sandbox.window.testApi;
}

test('identical live reads share one fetch', async () => {
  let count = 0, release;
  const api = harness(() => {
    count++;
    return new Promise(resolve => {release = () => resolve({ok: true, json: async () => ({value: 7})});});
  });
  const a = api('/query'), b = api('/query');
  release();
  assert.equal((await a).value, 7);
  assert.equal((await b).value, 7);
  assert.equal(count, 1);
});

test('repeating an aborted search starts a fresh request instead of reusing rejection', async () => {
  let count = 0;
  const api = harness((_url, options) => {
    count++;
    if (count === 1) return new Promise((_resolve, reject) =>
      options.signal.addEventListener('abort', () => reject(new DOMException('Cancelled', 'AbortError'))));
    return Promise.resolve({ok: true, json: async () => ({value: 'fresh'})});
  });
  const oldController = new AbortController();
  const old = api('/same-query', undefined, oldController.signal);
  const rejected = assert.rejects(old, {name: 'AbortError'});
  oldController.abort();
  const fresh = await api('/same-query', undefined, new AbortController().signal);
  await rejected;
  assert.equal(fresh.value, 'fresh');
  assert.equal(count, 2);
});
