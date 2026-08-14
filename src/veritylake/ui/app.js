'use strict';

const el = (id) => document.getElementById(id);

function node(tag, text, cls) {
  const item = document.createElement(tag);
  item.textContent = text;
  if (cls) item.className = cls;
  return item;
}

function setStatus(target, text, state) {
  target.textContent = text;
  target.dataset.state = state;
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'X-API-Key': el('key').value.trim(),
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`Request failed (${response.status})`);
  }
  if (!response.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`);
  }
  return data;
}

async function health() {
  try {
    const response = await fetch('/readyz');
    if (response.ok) {
      setStatus(el('health'), 'Ready to retrieve', 'ready');
    } else {
      setStatus(el('health'), 'Release preparing', 'waiting');
    }
  } catch {
    setStatus(el('health'), 'Service offline', 'error');
  }
}

async function catalog() {
  const refresh = el('refresh');
  refresh.disabled = true;
  refresh.textContent = 'Loading...';
  try {
    const data = await request('/catalog');
    el('snapshot-message').textContent = 'This quality-gated release is currently serving all retrieval requests.';
    el('snapshot').replaceChildren();
    const details = [
      ['Release', data.run_id.slice(0, 12)],
      ['Documents', data.tables.silver.rows],
      ['Evidence chunks', data.vector_count],
      ['Encoder', data.embedding_identity.name],
      ['Published', new Date(data.published_at).toLocaleString()]
    ];
    for (const [label, value] of details) {
      el('snapshot').append(node('dt', label), node('dd', String(value)));
    }

    el('checks').replaceChildren();
    for (const [stage, report] of Object.entries(data.quality)) {
      const row = node('div', '', 'check');
      row.append(
        node('span', `${stage.toUpperCase()} quality gate`),
        node('span', report.passed ? 'PASSED' : 'FAILED')
      );
      el('checks').append(row);
    }
  } catch (error) {
    el('snapshot-message').textContent = error.message;
    el('snapshot').replaceChildren();
    el('checks').replaceChildren();
  } finally {
    refresh.disabled = false;
    refresh.textContent = 'Refresh';
    await health();
  }
}

async function ask() {
  const question = el('question').value.trim();
  if (!question) {
    el('question').focus();
    return;
  }

  const button = el('ask');
  button.disabled = true;
  button.querySelector('span').textContent = 'Retrieving evidence...';
  el('result').hidden = false;
  el('answer').textContent = '';
  el('sources').replaceChildren();
  el('provenance').textContent = '';
  setStatus(el('answer-status'), 'Working', 'waiting');
  el('result').scrollIntoView({behavior: 'smooth', block: 'start'});

  try {
    const data = await request('/ask', {
      method: 'POST',
      body: JSON.stringify({question, top_k: Number(el('top-k').value)})
    });

    el('answer').textContent = data.answer;
    setStatus(
      el('answer-status'),
      data.status === 'answered' ? 'Grounded answer' : data.status,
      data.status === 'answered' ? 'ready' : 'waiting'
    );

    for (const source of data.sources) {
      const card = node('article', '', 'source');
      card.append(
        node('h3', `[${source.source_id}] ${source.title}`),
        node('div', Number.isFinite(source.distance) ? `retrieval distance · ${source.distance.toFixed(4)}` : 'retrieved evidence', 'source-meta'),
        node('blockquote', source.quote)
      );

      try {
        const url = new URL(source.url);
        if (['http:', 'https:'].includes(url.protocol)) {
          const link = node('a', 'Open original source ↗');
          link.href = url.href;
          link.target = '_blank';
          link.rel = 'noopener noreferrer';
          card.append(link);
        }
      } catch {
        // Invalid external URLs are intentionally not rendered as links.
      }

      card.append(node(
        'small',
        `Chunk ${source.chunk_id.slice(0, 12)} · Silver offsets ${source.char_start}–${source.char_end}`
      ));
      el('sources').append(card);
    }

    el('provenance').textContent =
      `RELEASE ${data.run_id.slice(0, 12)}  ·  MODEL ${data.generation_model}  ·  ${data.citation_validation}`;
    await catalog();
  } catch (error) {
    el('answer').textContent = error.message;
    setStatus(el('answer-status'), 'Unavailable', 'error');
  } finally {
    button.disabled = false;
    button.querySelector('span').textContent = 'Retrieve & answer';
  }
}

el('refresh').addEventListener('click', catalog);
el('ask').addEventListener('click', ask);
el('question').addEventListener('input', () => {
  el('char-count').textContent = `${el('question').value.length.toLocaleString()} / 1,000`;
});
el('question').addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    ask();
  }
});

health();
