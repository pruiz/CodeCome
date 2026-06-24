const API_BASE = '/api';
const TOKEN_KEY = 'codecome_access_token';

function authHeaders(extra = {}) {
  const token = window.localStorage?.getItem(TOKEN_KEY);
  return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
}

async function parseResponse(res, fallbackMessage = 'Request failed') {
  const text = await res.text();
  let data = null;

  if (text) {
    try {
      data = JSON.parse(text);
    } catch (_) {
      data = { detail: text };
    }
  }

  if (!res.ok) {
    throw new Error(data?.detail || fallbackMessage);
  }

  return data;
}

export const auditsApi = {
  create: (data) => {
    return fetch(`${API_BASE}/audits/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(res => parseResponse(res, 'Failed to create audit'));
  },
  uploadZip: (formData) => {
    return fetch(`${API_BASE}/audits/upload-zip/?name=${encodeURIComponent(formData.name)}`, {
      method: 'POST',
      body: formData.file
    }).then(res => parseResponse(res, 'Failed to upload audit'));
  },
  list: (params = {}) => {
    const query = new URLSearchParams({ skip: params.skip || 0, limit: params.limit || 20 });
    if (params.status) query.set('status', params.status);
    return fetch(`${API_BASE}/audits/?${query}`).then(res => parseResponse(res, 'Failed to list audits'));
  },
  get: (id) => {
    return fetch(`${API_BASE}/audits/${id}`).then(res => parseResponse(res, 'Audit not found'));
  },
  update: (id, data) => {
    return fetch(`${API_BASE}/audits/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(res => parseResponse(res, 'Failed to update audit'));
  },
  delete: (id) => {
    return fetch(`${API_BASE}/audits/${id}`, { method: 'DELETE' });
  },
  start: (id) => {
    return fetch(`${API_BASE}/audits/${id}/start`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to start audit'));
  },
  runPhase: (id, phase) => {
    return fetch(`${API_BASE}/audits/${id}/run-phase?phase=${encodeURIComponent(phase)}`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to run phase'));
  },
  pause: (id) => {
    return fetch(`${API_BASE}/audits/${id}/pause`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to pause audit'));
  },
};

export const findingsApi = {
  list: (auditId, params = {}) => {
    const query = new URLSearchParams({ skip: params.skip || 0, limit: params.limit || 50 });
    if (auditId) query.set('audit_id', auditId);
    if (params.status) query.set('status', params.status);
    if (params.severity) query.set('severity', params.severity);
    if (params.category) query.set('category', params.category);
    return fetch(`${API_BASE}/findings/?${query}`).then(res => parseResponse(res, 'Failed to list findings'));
  },
  get: (id, auditId) => {
    const query = auditId ? `?audit_id=${encodeURIComponent(auditId)}` : '';
    return fetch(`${API_BASE}/findings/${id}${query}`).then(res => parseResponse(res, 'Failed to load finding'));
  },
  update: (id, auditId, data) => {
    const query = auditId ? `?audit_id=${encodeURIComponent(auditId)}` : '';
    return fetch(`${API_BASE}/findings/${id}${query}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }).then(res => parseResponse(res, 'Failed to update finding'));
  },
  listEvidence: (id) => fetch(`${API_BASE}/findings/${id}/evidence`).then(res => parseResponse(res, 'Failed to load evidence')),
};

export const previewApi = {
  getConfig: () => fetch(`${API_BASE}/preview/config`).then(res => parseResponse(res, 'Failed to load preview config')),
  updateConfig: (prompt) => fetch(`${API_BASE}/preview/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt })
  }).then(res => parseResponse(res, 'Failed to save preview config')),
};

export const logsApi = {
  list: (auditId, params = {}) => {
    const query = new URLSearchParams({ skip: params.skip || 0, limit: params.limit || 100 });
    if (params.level) query.set('level', params.level);
    if (params.phase) query.set('phase', params.phase);
    return fetch(`${API_BASE}/logs/${auditId}?${query}`).then(res => parseResponse(res, 'Failed to load logs'));
  },
  tokenSummary: (auditId, phase) => {
    const query = new URLSearchParams();
    if (phase) query.set('phase', phase);
    return fetch(`${API_BASE}/logs/${auditId}/token-summary?${query}`).then(res => parseResponse(res, 'Failed to load token summary'));
  },
};

export const phasesApi = {
  list: (auditId) => fetch(`${API_BASE}/phases/?audit_id=${auditId}`).then(res => parseResponse(res, 'Failed to list phases')),
  get: (execId) => fetch(`${API_BASE}/phases/${execId}`).then(res => parseResponse(res, 'Failed to load phase execution')),
  findings: (execId) => fetch(`${API_BASE}/phases/${execId}/findings`).then(res => parseResponse(res, 'Failed to load phase findings')),
  triages: (execId) => fetch(`${API_BASE}/phases/${execId}/triages`).then(res => parseResponse(res, 'Failed to load phase triages')),
  runTriage: (execId) => fetch(`${API_BASE}/phases/${execId}/triage`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to queue phase triage')),
  applyTriage: (triageId, data = {}) => fetch(`${API_BASE}/phases/triages/${triageId}/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(res => parseResponse(res, 'Failed to apply phase triage')),
  retry: (execId) => fetch(`${API_BASE}/phases/${execId}/retry`, {
    method: 'POST'
  }).then(res => parseResponse(res, 'Failed to retry phase')),
};

export const questionsApi = {
  list: (params = {}) => {
    const query = new URLSearchParams();
    if (params.audit_id) query.set('audit_id', params.audit_id);
    if (params.phase_execution_id) query.set('phase_execution_id', params.phase_execution_id);
    if (params.status) query.set('status', params.status);
    return fetch(`${API_BASE}/questions/?${query}`).then(res => parseResponse(res, 'Failed to list questions'));
  },
  answer: (id, data) => fetch(`${API_BASE}/questions/${id}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(res => parseResponse(res, 'Failed to answer question')),
  dismiss: (id) => fetch(`${API_BASE}/questions/${id}/dismiss`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to dismiss question')),
  autoAnswer: (id) => fetch(`${API_BASE}/questions/${id}/auto-answer`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to auto-answer question')),
  writeAnswerContext: (auditId) => fetch(`${API_BASE}/questions/audits/${auditId}/write-answer-context`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to write answer context')),
};

export const auditQuestionApi = {
  continueAfterQuestions: (auditId) => fetch(`${API_BASE}/audits/${auditId}/continue-after-questions`, { method: 'POST' }).then(res => parseResponse(res, 'Failed to continue audit')),
};

export const usersApi = {
  list: (params = {}) => {
    const query = new URLSearchParams({ skip: params.skip || 0, limit: params.limit || 100 });
    if (params.active !== undefined) query.set('active', String(params.active));
    if (params.is_llm_user !== undefined) query.set('is_llm_user', String(params.is_llm_user));
    return fetch(`${API_BASE}/users/?${query}`).then(res => parseResponse(res, 'Failed to list users'));
  },
  create: (data) => fetch(`${API_BASE}/users/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(res => parseResponse(res, 'Failed to create user')),
  update: (id, data) => fetch(`${API_BASE}/users/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(res => parseResponse(res, 'Failed to update user')),
};

export const authApi = {
  tokenKey: TOKEN_KEY,
  login: (username, password) => fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  }).then(async (res) => {
    const data = await parseResponse(res, 'Failed to login');
    if (data.access_token) window.localStorage?.setItem(TOKEN_KEY, data.access_token);
    return data;
  }),
  me: () => fetch(`${API_BASE}/auth/me`, { headers: authHeaders() }).then(res => parseResponse(res, 'Failed to load current user')),
  logout: () => window.localStorage?.removeItem(TOKEN_KEY),
  getToken: () => window.localStorage?.getItem(TOKEN_KEY),
};

export const workersApi = {
  list: () => fetch(`${API_BASE}/workers/`).then(res => parseResponse(res, 'Failed to list workers')),
  get: (id) => fetch(`${API_BASE}/workers/${id}`).then(res => parseResponse(res, 'Failed to load worker')),
  checks: (id) => fetch(`${API_BASE}/workers/${id}/checks`).then(res => parseResponse(res, 'Failed to load worker checks')),
  bootstrapScript: () => fetch(`${API_BASE}/workers/bootstrap-script`).then(res => {
    if (!res.ok) throw new Error('Failed to load bootstrap script');
    return res.text();
  }),
  getOpenCodeConfig: () => fetch(`${API_BASE}/workers/opencode-config`).then(res => parseResponse(res, 'Failed to load OpenCode config')),
  updateOpenCodeConfig: (content) => fetch(`${API_BASE}/workers/opencode-config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  }).then(res => parseResponse(res, 'Failed to save OpenCode config')),
  create: (data) => fetch(`${API_BASE}/workers/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }).then(res => parseResponse(res, 'Failed to create worker')),
  update: (id, data) => fetch(`${API_BASE}/workers/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  }).then(res => parseResponse(res, 'Failed to update worker')),
  delete: (id) => fetch(`${API_BASE}/workers/${id}`, { method: 'DELETE' }).then(res => {
    if (!res.ok) throw new Error('Failed to delete worker');
    return true;
  }),
};
