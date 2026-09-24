const API = '/api';

async function request(path, { body, headers, ...rest } = {}) {
  const isForm = body instanceof FormData;
  const init = {
    ...rest,
    headers: { ...(isForm ? {} : { 'Content-Type': 'application/json' }), ...headers },
  };
  if (body !== undefined) init.body = isForm ? body : JSON.stringify(body);

  let res;
  try {
    res = await fetch(`${API}${path}`, init);
  } catch (err) {
    if (err.name === 'AbortError') throw err;
    // fetch rejects only when no response arrived at all — offline, server
    // down, or (commonly on phones) the request was cut off while the app was
    // in the background. The browser's wording for that ("Failed to fetch",
    // "Load failed") means nothing to the learner.
    const netErr = new Error('Network error — check your connection and try again.');
    netErr.cause = err;
    throw netErr;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    // FastAPI validation errors (422) carry a list of {loc, msg, ...} objects.
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg).join('; ')
      : body.detail;
    const err = new Error(detail || 'Request failed');
    // Callers branch on this — cloze treats a 422 as "skip this item" rather
    // than an error worth interrupting the session for.
    err.status = res.status;
    throw err;
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
  // enrich=true has the server generate usage notes + example sentences at save
  // time, so the item matches what the import flow produces. Costs one AI call.
  createItem: (data, { enrich = false } = {}) =>
    request(`/items/${enrich ? '?enrich=true' : ''}`, { method: 'POST', body: data }),
  updateItem: (id, data) => request(`/items/${id}`, { method: 'PUT', body: data }),
  deleteItem: (id) => request(`/items/${id}`, { method: 'DELETE' }),
  // Pull an item out of the review queue without losing it.
  suspendItem: (id) => request(`/items/${id}/suspend`, { method: 'POST' }),
  // reset=true (the default) clears the review history, so a reworked card
  // doesn't re-trip the leech threshold on its first lapse.
  unsuspendItem: (id, { reset = true } = {}) =>
    request(`/items/${id}/unsuspend?reset=${reset}`, { method: 'POST' }),

  // Study
  getDueItems: (params = {}) => request(`/study/due?${qs(params)}`),
  // Extra reps outside the SRS schedule — any active item, not just due ones.
  getPracticeItems: (params = {}) => request(`/study/practice?${qs(params)}`),
  // Passing sessionId folds the review into the session's counters server-side,
  // so progress survives abandoning the session part-way. practice=true skips
  // SRS scheduling server-side, so it can't reschedule a card early.
  // card='reading' rates the item's separate kanji-reading schedule instead.
  reviewItem: (itemId, rating, sessionId = null, practice = false, card = 'meaning') =>
    request('/study/review', {
      method: 'POST',
      body: {
        item_id: itemId,
        rating,
        card,
        ...(sessionId != null && { session_id: sessionId }),
        ...(practice && { practice: true }),
      },
    }),
  // Kanji-reading drill queues: due reading cards topped up with new ones,
  // each item carrying the other library words that share its kanji.
  getReadingDue: (params = {}) => request(`/study/reading/due?${qs(params)}`),
  getReadingPractice: (params = {}) => request(`/study/reading/practice?${qs(params)}`),
  // Readings, level, parts, mnemonic and origin for each kanji of an item,
  // plus which reading this word uses. The first word to contain an uncached
  // kanji costs one AI call; after that it comes from the server's cache.
  getItemKanji: (itemId) => request(`/kanji/item/${itemId}`),
  getDashboard: () => request('/study/dashboard'),
  getHistory: (days = 60) => request(`/study/history?days=${days}`),
  startSession: (mode) => request(`/study/session/start?mode=${mode}`, { method: 'POST' }),
  // For modes that aren't item reviews (conversation turns).
  sessionProgress: (id, { reviewed = 0, correct = 0, hard = 0 }) =>
    request(`/study/session/${id}/progress`, { method: 'POST', body: { reviewed, correct, hard } }),
  // Counts are optional — omit them to just close the session without
  // overwriting the progress already recorded per review.
  endSession: (id) => request(`/study/session/${id}/end`, { method: 'POST' }),

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
  evaluateAnswer: (userAnswer, expectedAnswer, prompt) =>
    request('/generate/evaluate', { method: 'POST', body: { user_answer: userAnswer, expected_answer: expectedAnswer, prompt } }),

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
