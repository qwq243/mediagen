/* Immediate browser recovery + debounced, versioned project drafts.
   This module never applies a proposal, confirms a stage or starts production. */
(function () {
  'use strict';
  function createFormAutosave({ state, stage, patch, patchKeys, formRoot = () => '#view', api, onSaved, onDirty, resize }) {
    const entries = new Map(), timers = new Map();
    let queue = Promise.resolve(), recoveryFailed = false;
    const key = name => 'mediagen-form-v1:' + state().job_id + ':' + name;
    const signature = entry => JSON.stringify([entry.fields, entry.patch, entry.comment]);
    const read = name => {
      try { return JSON.parse(localStorage.getItem(key(name)) || 'null'); }
      catch (_) { return null; }
    };
    function status(name, text, warning = false) {
      if (stage() !== name) return;
      document.querySelectorAll('[data-autosave-status]').forEach(el => {
        el.textContent = text;
        el.classList.toggle('warning', warning);
      });
    }
    function keep(entry) {
      entries.set(entry.stage, entry);
      try {
        localStorage.setItem(key(entry.stage), JSON.stringify(entry));
        recoveryFailed = false;
        return true;
      } catch (_) {
        recoveryFailed = true;
        status(entry.stage, '本机保存失败，正在保存到项目', true);
        return false;
      }
    }
    function values() {
      const result = {};
      const root = formRoot();
      document.querySelectorAll(`${root} input[id],${root} textarea[id],${root} select[id]`).forEach(el => {
        result[el.id] = el.type === 'checkbox' ? el.checked : el.value;
      });
      const mode = document.querySelector('input[name="page-count-mode"]:checked');
      if (mode) result['page-count-mode'] = mode.value;
      return result;
    }
    function apply(fields) {
      for (const [id, value] of Object.entries(fields || {})) {
        if (id === 'page-count-mode') {
          document.querySelectorAll('input[name="page-count-mode"]').forEach(el => { el.checked = el.value === value; });
          continue;
        }
        const el = document.getElementById(id);
        if (!el || !el.closest(formRoot())) continue;
        if (el.type === 'checkbox') el.checked = value === true;
        else el.value = value; // Empty strings are intentional edits, not missing values.
      }
      resize();
    }
    function capture() {
      const name = stage(), s = state();
      if (!s?.job_id || !['stage1', 'stage2'].includes(name) || !document.querySelector('#stage-comment')) return;
      const old = entries.get(name), currentPatch = patch(name);
      const formPatch = patchKeys ? { ...old?.patch } : {};
      // Split views own disjoint top-level proposal keys. A revert removes only
      // the active surface's patch, never an unmounted surface's edits.
      for (const key of patchKeys?.(name) || []) delete formPatch[key];
      Object.assign(formPatch, currentPatch);
      const comment = document.querySelector('#stage-comment').value;
      const entry = { ...old, stage: name, proposal_hash: old?.proposal_hash || s.proposal_hash,
        fields: { ...old?.fields, ...values() }, patch: formPatch, comment, dirty: true, updated_at: Date.now() };
      keep(entry);
      onDirty(Boolean(Object.keys(formPatch).length || comment));
      status(name, '正在保存草稿…');
      clearTimeout(timers.get(name));
      timers.set(name, setTimeout(() => flush(name).catch(() => {}), 650));
    }
    async function send(name, submit) {
      const entry = entries.get(name);
      if (!entry || (!entry.dirty && !submit)) return;
      if (entry.proposal_hash !== state().proposal_hash || entry.conflict) {
        status(name, '草稿已保留，版本变化需与 Agent 对齐', true);
        throw Error('草稿与当前版本不同，已保留修改，请与 Agent 对齐后再提交');
      }
      const sent = signature(entry);
      const clear = !Object.keys(entry.patch).length && !entry.comment;
      status(name, '正在保存草稿…');
      try {
        const result = await api('/api/v3/form-draft', {
          stage: name, patch: entry.patch, comment: entry.comment,
          form_values: entry.fields, draft_id: entry.draft_id || null,
          draft_version: entry.draft_version || 0, submit, clear
        });
        onSaved(result);
        const latest = entries.get(name);
        const record = result.record, editable = record?.status === 'draft';
        latest.draft_id = editable ? record.id : null;
        latest.draft_version = editable ? record.details.autosave_version : 0;
        latest.dirty = signature(latest) !== sent;
        latest.saved = record?.status || 'unchanged';
        keep(latest);
        if (!latest.dirty) {
          recoveryFailed = false; // The server copy is sufficient recovery if local storage is unavailable.
          status(name, record?.details?.validation_errors?.length ? '草稿已保存，页数待补全' :
            record?.status === 'submitted' ? '已提交，待对齐' : clear ? '' : '草稿已保存',
            !!record?.details?.validation_errors?.length);
        }
        return result;
      } catch (error) {
        status(name, recoveryFailed ? '保存失败，请勿关闭页面' : '已保存在本机，项目同步失败', true);
        throw error;
      }
    }
    function flush(name = stage(), submit = false) {
      clearTimeout(timers.get(name));
      queue = queue.catch(() => {}).then(() => send(name, submit));
      return queue;
    }
    function restore() {
      const name = stage(), s = state();
      if (!s?.job_id || !['stage1', 'stage2'].includes(name) || !document.querySelector('#stage-comment')) return;
      const server = s.pending.filter(x => x.kind === 'form_autosave' && x.stage === name)
        .sort((a, b) => b.at.localeCompare(a.at))[0];
      const local = read(name);
      let entry = null;
      if (local?.dirty) {
        entry = local;
        if (server && server.id === local.draft_id &&
            server.details.autosave_version !== local.draft_version) entry.conflict = true;
      } else if (server) {
        entry = { stage: name, proposal_hash: server.base_proposal_hash,
          fields: server.details.form_values, patch: server.patch, comment: server.comment,
          draft_id: server.status === 'draft' ? server.id : null,
          draft_version: server.status === 'draft' ? server.details.autosave_version : 0,
          dirty: false, saved: server.status };
      } else {
        // A saved draft no longer pending has been applied/discarded by Agent.
        try { localStorage.removeItem(key(name)); } catch (_) {}
      }
      if (!entry) { entries.delete(name); return; }
      entries.set(name, entry);
      apply(entry.fields);
      onDirty(Boolean(Object.keys(entry.patch).length || entry.comment));
      if (entry.proposal_hash !== s.proposal_hash || entry.conflict) {
        status(name, '已恢复旧草稿，需与 Agent 对齐', true);
      } else {
        status(name, entry.saved === 'submitted' ? '已提交，待对齐' : '草稿已恢复');
        if (entry.dirty) timers.set(name, setTimeout(() => flush(name).catch(() => {}), 650));
      }
    }
    function getPatch(name = stage()) {
      const s = state(), inMemory = entries.get(name), local = inMemory?.dirty ? inMemory : read(name);
      const server = s.pending.filter(x => x.kind === 'form_autosave' && x.stage === name)
        .sort((a, b) => b.at.localeCompare(a.at))[0];
      if (local?.dirty && server && server.id === local.draft_id &&
          server.details.autosave_version !== local.draft_version) return {};
      const entry = local?.dirty ? local : server ? {
        proposal_hash: server.base_proposal_hash, patch: server.patch
      } : null;
      return entry && !entry.conflict && entry.proposal_hash === s.proposal_hash ?
        structuredClone(entry.patch) : {};
    }
    function getComment(name = stage()) {
      const entry = entries.get(name);
      if (entry) return entry.comment || '';
      const server = state().pending.filter(x => x.kind === 'form_autosave' && x.stage === name)
        .sort((a, b) => b.at.localeCompare(a.at))[0];
      return server?.comment || '';
    }
    return { capture, restore, flush, getPatch, getComment, needsLeaveWarning: () => recoveryFailed };
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { createFormAutosave };
  if (typeof window !== 'undefined') window.createFormAutosave = createFormAutosave;
})();
