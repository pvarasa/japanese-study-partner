const API = '/api';

async function request(path, { body, headers, ...rest } = {}) {
  const isForm = body instanceof FormData;
  const init = {
    ...rest,
    headers: { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...headers },
  };
  if (body !== undefined) init.body = isForm ? body : JSON.stringify(body);

  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

const form = (entries) => {
  const fd = new FormData();
  for (const [k, v] of Object.entries(entries)) {
    if (v !== null && v !== undefined) fd.append(k, v);
  }
  return fd;
};

const qs = (params) => new URLSearchParams(params).toString();

export const api = {
  // Items
  getItems: (params = {}) => request(`/items/?${qs(params)}`),
  getItem: (id) => request(`/items/${id}`),
  createItem: (data) => request('/items/', { method: 'POST', body: data }),
  updateItem: (id, data) => request(`/items/${id}`, { method: 'PUT', body: data }),
  deleteItem: (id) => request(`/items/${id}`, { method: 'DELETE' }),

  // Study
  getDueItems: (params = {}) => request(`/study/due?${qs(params)}`),
  reviewItem: (itemId, rating) =>
    request('/study/review', { method: 'POST', body: { item_id: itemId, rating } }),
  getDashboard: () => request('/study/dashboard'),
  startSession: (mode) => request(`/study/session/start?mode=${mode}`, { method: 'POST' }),
  endSession: (id, reviewed, correct) =>
    request(`/study/session/${id}/end?items_reviewed=${reviewed}&items_correct=${correct}`, { method: 'POST' }),

  // Ingest
  ingestText: (content) => request('/ingest/text', { method: 'POST', body: form({ content }) }),
  ingestUrl: (url) => request('/ingest/url', { method: 'POST', body: form({ url }) }),
  ingestPdf: (file) => request('/ingest/pdf', { method: 'POST', body: form({ file }) }),
  saveIngested: (sourceTitle, sourceType, sourceUrl, items) =>
    request('/ingest/save', { method: 'POST', body: form({
      source_title: sourceTitle,
      source_type: sourceType,
      source_url: sourceUrl,
      items_json: JSON.stringify(items),
    }) }),

  // Furigana
  furigana: (texts) => request('/furigana/annotate', { method: 'POST', body: { texts } }),
  tokenize: (text, words) => request('/furigana/tokenize', { method: 'POST', body: { text, words } }),
  lookupWord: (surface, lemma, context, isPhrase = false) =>
    request('/furigana/lookup', { method: 'POST', body: { surface, lemma, context, is_phrase: isPhrase } }),

  // Generate
  generateQuestion: (itemId, mode) =>
    request(`/generate/question?item_id=${itemId}&mode=${mode}`, { method: 'POST' }),
  generateExampleSentence: (itemId) =>
    request(`/generate/example-sentence?item_id=${itemId}`, { method: 'POST' }),
  generateReading: (prompt) =>
    request('/generate/reading', { method: 'POST', body: form({ prompt }) }),

  // Features
  getFeatures: () => request('/features'),

  // Settings
  getSettings: () => request('/settings/'),
  updateSettings: (data) => request('/settings/', { method: 'PUT', body: data }),

  // Converse
  converseStart: () => request('/converse/start', { method: 'POST' }),
  converseReply: (history, userText) =>
    request('/converse/reply', { method: 'POST', body: { history, user_text: userText } }),

  // Transcribe
  transcribe: (blob, filename = 'audio.webm') =>
    request('/transcribe/', { method: 'POST', body: form({ audio: new File([blob], filename, { type: blob.type }) }) }),
};
