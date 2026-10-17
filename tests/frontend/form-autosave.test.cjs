const test = require('node:test');
const assert = require('node:assert/strict');
const { createFormAutosave } = require('../../scripts/static/ppt-workbench/form-autosave.js');

function setup(options = {}) {
  const memory = new Map(), requests = [];
  global.localStorage = {
    getItem: key => memory.get(key) || null,
    setItem: (key, value) => memory.set(key, value),
    removeItem: key => memory.delete(key)
  };
  const fields = Object.fromEntries(['content_divergence', 'stage-comment'].map(id =>
    [id, { id, value: '', type: 'textarea', closest: () => true }]));
  const label = { textContent: '', classList: { toggle() {} } };
  global.document = {
    querySelector: selector => fields[selector.slice(1)] || null,
    querySelectorAll: selector => selector === '[data-autosave-status]' ? [label] :
      selector.startsWith('#view input') ? Object.values(fields) : [],
    getElementById: id => fields[id] || null
  };
  let activeStage = 'stage1', failed = false;
  const state = { job_id: 'fixture', proposal_hash: 'base', pending: [], revision: 1 };
  const draft = createFormAutosave({
    state: () => state, stage: () => activeStage,
    patch: () => fields.content_divergence.value === 'baseline' ? {} :
      { communication: { content_divergence: fields.content_divergence.value } },
    ...options,
    resize() {}, onDirty() {},
    async api(path, body) {
      requests.push({ path, ...structuredClone(body) });
      if (failed) throw Error('offline');
      return { revision: state.revision + 1, record: {
        id: body.draft_id || 'rev-test', stage: body.stage,
        kind: 'form_autosave', status: body.clear ? 'discarded' : body.submit ? 'submitted' : 'draft',
        patch: body.patch, comment: body.comment, base_proposal_hash: 'base', at: '2026-10-15',
        details: { form_values: body.form_values, autosave_version: body.draft_version + 1 }
      } };
    },
    onSaved(result) {
      state.revision = result.revision;
      state.pending = result.record.status === 'discarded' ? [] : [result.record];
    }
  });
  return { draft, state, fields, memory, requests, label,
    stage: value => { activeStage = value; }, offline: () => { failed = true; } };
}

test('typing and deleting are immediately recoverable before a network request', async () => {
  const f = setup();
  f.fields.content_divergence.value = '刚输入';
  f.draft.capture();
  assert.equal(JSON.parse([...f.memory.values()][0]).fields.content_divergence, '刚输入');
  f.fields.content_divergence.value = '';
  f.draft.capture();
  assert.equal(JSON.parse([...f.memory.values()][0]).fields.content_divergence, '');
  await f.draft.flush();
  assert.equal(f.requests.length, 1);
  assert.equal(f.requests[0].patch.communication.content_divergence, '');
});

test('restore from the server includes blank fields and updates the same draft', async () => {
  const f = setup();
  f.state.pending = [{ id: 'rev-server', stage: 'stage1', kind: 'form_autosave', status: 'draft',
    patch: { communication: { content_divergence: '' } }, comment: '',
    base_proposal_hash: 'base', at: '2026-10-15',
    details: { form_values: { content_divergence: '' }, autosave_version: 3 } }];
  f.fields.content_divergence.value = 'baseline';
  f.draft.restore();
  assert.equal(f.fields.content_divergence.value, '');
  f.fields.content_divergence.value = '再修改';
  f.draft.capture();
  await f.draft.flush();
  assert.equal(f.requests[0].draft_id, 'rev-server');
  assert.equal(f.requests[0].draft_version, 3);
});

test('navigation does not redirect a queued stage1 edit to another stage', async () => {
  const f = setup();
  f.fields.content_divergence.value = '本阶段修改';
  f.draft.capture();
  f.stage('assets');
  await f.draft.flush('stage1');
  assert.equal(f.requests[0].stage, 'stage1');
  assert.equal(f.requests[0].form_values.content_divergence, '本阶段修改');
});

test('offline failure retains the local draft instead of resetting the form', async () => {
  const f = setup();
  f.offline();
  f.fields.content_divergence.value = '断网草稿';
  f.draft.capture();
  await assert.rejects(f.draft.flush(), /offline/);
  assert.equal(JSON.parse([...f.memory.values()][0]).fields.content_divergence, '断网草稿');
  assert.equal(f.draft.needsLeaveWarning(), false);
  assert.match(f.label.textContent, /本机/);
});

test('proposal changes do not silently overwrite the new base', async () => {
  const f = setup();
  f.fields.content_divergence.value = '旧版本草稿';
  f.draft.capture();
  f.state.proposal_hash = 'new-base';
  await assert.rejects(f.draft.flush(), /当前版本不同/);
  assert.equal(f.requests.length, 0);
  assert.equal(JSON.parse([...f.memory.values()][0]).dirty, true);
});

test('submitted drafts remain submitted; later edits create a new draft', async () => {
  const f = setup();
  f.fields.content_divergence.value = '待提交';
  f.draft.capture();
  await f.draft.flush('stage1', true);
  f.fields.content_divergence.value = '提交后的新想法';
  f.draft.capture();
  await f.draft.flush();
  assert.equal(f.requests[0].submit, true);
  assert.equal(f.requests[1].draft_id, null);
});

test('split stage2 surfaces preserve one shared draft, including edits reverted on one surface', async () => {
  let surface = 'settings';
  let currentPatch = { design: { typography: { body: '新字体' } } };
  const f = setup({
    patchKeys: () => surface === 'settings' ? ['design'] : ['pages'],
    patch: () => currentPatch
  });
  f.stage('stage2');
  delete f.fields.content_divergence;
  f.fields['font-body'] = {id: 'font-body', value: '新字体', closest: () => true};
  f.draft.capture();
  assert.deepEqual(f.draft.getPatch('stage2'), currentPatch);
  await f.draft.flush();
  delete f.fields['font-body'];
  f.fields['story-P01-page_text'] = {id: 'story-P01-page_text', value: '逐页修改', closest: () => true};
  surface = 'pages';
  currentPatch = { pages: [{ page_id: 'P01', page_text: '逐页修改' }] };
  f.draft.restore();
  f.draft.capture();
  await f.draft.flush();
  assert.deepEqual(f.requests[1].patch, {
    design: { typography: { body: '新字体' } }, pages: currentPatch.pages
  });
  assert.equal(f.requests[1].draft_id, 'rev-test');
  assert.equal(f.requests[1].draft_version, 1);
  assert.equal(f.requests[1].form_values['font-body'], '新字体');
  assert.equal(f.requests[1].form_values['story-P01-page_text'], '逐页修改');
  currentPatch = {};
  f.draft.capture();
  await f.draft.flush();
  assert.deepEqual(f.draft.getPatch('stage2'), {design: { typography: {body: '新字体'}}});
  f.state.proposal_hash = 'changed-base';
  assert.deepEqual(f.draft.getPatch('stage2'), {});
});

test('display never treats a conflicting local copy as the current shared configuration', () => {
  const f = setup();
  f.state.pending = [{ id: 'rev-test', stage: 'stage1', kind: 'form_autosave',
    status: 'draft', patch: {communication: {content_divergence: 'server copy'}},
    base_proposal_hash: 'base', at: '2026-10-15',
    details: {form_values: {}, autosave_version: 2} }];
  f.memory.set('mediagen-form-v1:fixture:stage1', JSON.stringify({
    stage: 'stage1', proposal_hash: 'base', dirty: true, draft_id: 'rev-test',
    draft_version: 1, fields: {}, patch: {communication: {content_divergence: 'stale copy'}}
  }));
  assert.deepEqual(f.draft.getPatch('stage1'), {});
});

test('configuration capture only serializes controls inside its form root', async () => {
  const f = setup({formRoot: () => '#global-settings'});
  const selectors = [];
  global.document.querySelectorAll = selector => {
    selectors.push(selector);
    return selector.startsWith('#global-settings input') ? Object.values(f.fields) : [];
  };
  f.stage('stage2');
  f.fields.content_divergence.value = 'scoped setting';
  f.draft.capture();
  await f.draft.flush();
  assert.ok(selectors.some(s => s === '#global-settings input[id],#global-settings textarea[id],#global-settings select[id]'));
  assert.equal(f.requests[0].form_values.content_divergence, 'scoped setting');
  assert.equal(f.requests[0].form_values['region-page-select'], undefined);
});
