(function () {
  "use strict";

  const extensionLanguages = {
    py: "python", js: "javascript", css: "css", html: "xml", sql: "sql",
    sh: "bash", yaml: "yaml", yml: "yaml", json: "json", toml: "ini",
    ini: "ini", xml: "xml", csv: "plaintext", md: "markdown", txt: "plaintext",
  };
  const textExtensions = new Set([...Object.keys(extensionLanguages), "gitignore"]);
  const state = { path: "", raw: "", mode: "rendered", request: 0, controller: null, root: "" };
  const valuableKey = /(?:^|_)(?:id|name|status|score|confidence|evidence|finding|summary|reason|eligible|classification|methodology|question|chapter|year|source|citation|locator|warning|gap|decision)(?:$|_)/i;

  function escapeHtml(value) {
    return value.replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }

  function extension(path) {
    const name = path.split("/").pop() || "";
    return name.includes(".") ? name.split(".").pop().toLowerCase() : name.toLowerCase();
  }

  function buildViewer() {
    const wrapper = document.createElement("div");
    wrapper.className = "repo-viewer-backdrop";
    wrapper.innerHTML = `<div class="repo-viewer-resizer" role="separator" aria-label="Resize file viewer" aria-orientation="vertical" tabindex="0"></div><section class="repo-viewer" role="dialog" aria-modal="true" aria-label="Repository file viewer">
      <header class="repo-viewer-header"><span class="repo-viewer-title"></span>
        <button class="repo-viewer-button" data-action="toggle" hidden>Source</button>
        <button class="repo-viewer-button" data-action="expand" hidden>Expand all</button>
        <button class="repo-viewer-button" data-action="collapse" hidden>Collapse all</button>
        <a class="repo-viewer-button" data-action="vscode">VS Code</a>
        <button class="repo-viewer-button" data-action="copy">Copy path</button>
        <button class="repo-viewer-button" data-action="close" aria-label="Close viewer">Close</button></header>
      <div class="repo-viewer-toolbar"><input class="repo-viewer-search" type="search" placeholder="Find in displayed file…"><button class="repo-viewer-button" data-action="find">Find next</button><span class="repo-viewer-meta"></span></div>
      <div class="repo-viewer-content"><p class="repo-viewer-message">Select a repository file.</p></div></section>`;
    document.body.appendChild(wrapper);
    wrapper.addEventListener("click", event => {
      if (event.target === wrapper || event.target.closest('[data-action="close"]')) closeViewer();
      if (event.target.closest('[data-action="copy"]')) navigator.clipboard.writeText(state.path);
      if (event.target.closest('[data-action="toggle"]')) toggleMarkdown();
      if (event.target.closest('[data-action="expand"]')) setJsonExpansion(true);
      if (event.target.closest('[data-action="collapse"]')) setJsonExpansion(false);
      if (event.target.closest('[data-action="find"]')) findNext(wrapper);
    });
    wrapper.querySelector(".repo-viewer-search").addEventListener("keydown", event => {
      if (event.key === "Enter") findNext(wrapper);
    });
    return wrapper;
  }

  const viewer = buildViewer();
  const content = viewer.querySelector(".repo-viewer-content");
  const title = viewer.querySelector(".repo-viewer-title");
  const meta = viewer.querySelector(".repo-viewer-meta");
  const toggle = viewer.querySelector('[data-action="toggle"]');
  const expand = viewer.querySelector('[data-action="expand"]');
  const collapse = viewer.querySelector('[data-action="collapse"]');
  const vscode = viewer.querySelector('[data-action="vscode"]');
  const resizer = viewer.querySelector(".repo-viewer-resizer");

  function closeViewer() {
    viewer.classList.remove("is-open");
    document.body.classList.remove("repo-viewer-open");
    history.replaceState(null, "", `${location.pathname}${location.search}`);
  }

  function resolveRepositoryPath(anchor) {
    if (anchor.protocol !== "http:" && anchor.protocol !== "https:") return null;
    if (anchor.origin !== location.origin) return null;
    const path = decodeURIComponent(anchor.pathname.replace(/^\//, ""));
    if (!path || path.endsWith("/")) return null;
    return path;
  }

  async function openPath(path) {
    const request = ++state.request;
    if (state.controller) state.controller.abort();
    state.controller = new AbortController();
    state.path = path;
    state.mode = "rendered";
    viewer.classList.add("is-open");
    document.body.classList.add("repo-viewer-open");
    title.textContent = path;
    content.innerHTML = '<p class="repo-viewer-message">Loading…</p>';
    toggle.hidden = extension(path) !== "md";
    expand.hidden = extension(path) !== "json";
    collapse.hidden = extension(path) !== "json";
    toggle.textContent = "Source";
    vscode.hidden = true;
    history.replaceState(null, "", `#view=${encodeURIComponent(path)}`);
    try {
      const response = await fetch(`/${path}`, { signal: state.controller.signal });
      if (request !== state.request) return;
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const length = Number(response.headers.get("content-length") || 0);
      if (length > 2_000_000) throw new Error("File is larger than the 2 MB viewer limit");
      state.raw = await response.text();
      if (request !== state.request) return;
      state.root = response.headers.get("X-Repository-Root") || state.root;
      if (state.root) {
        vscode.href = `vscode://file${encodeURI(state.root)}/${encodeURI(path)}`;
        vscode.hidden = false;
      }
      meta.textContent = `${state.raw.split("\n").length} lines · ${state.raw.length.toLocaleString()} characters`;
      render(path, state.raw);
    } catch (error) {
      if (error.name === "AbortError" || request !== state.request) return;
      content.innerHTML = `<p class="repo-viewer-message"><strong>Unable to open this file.</strong><br>${escapeHtml(String(error))}<br><br>Run <code>python scripts/serve_design_reviews.py</code> and open the localhost URL.</p>`;
    }
  }

  function render(path, raw) {
    const ext = extension(path);
    if (!textExtensions.has(ext)) {
      content.innerHTML = `<p class="repo-viewer-message">This format uses the browser's native viewer. <a href="/${escapeHtml(path)}" target="_blank">Open it in a new tab</a>.</p>`;
    } else if (ext === "md" && state.mode === "rendered") renderMarkdown(raw);
    else if (ext === "json" && state.mode === "rendered") renderJson(raw);
    else if (ext === "csv" && state.mode === "rendered") renderCsv(raw);
    else renderSource(raw, extensionLanguages[ext] || "plaintext");
  }

  function renderSource(raw, language) {
    let highlighted = escapeHtml(raw);
    if (window.hljs) {
      try { highlighted = window.hljs.highlight(raw, { language }).value; } catch (_) { /* plain fallback */ }
    }
    const numbers = raw.split("\n").map((_, index) => index + 1).join("\n");
    content.innerHTML = `<div class="repo-viewer-source"><div class="repo-viewer-lines">${numbers}</div><pre class="repo-viewer-code"><code class="hljs language-${language}">${highlighted}</code></pre></div>`;
  }

  function renderMarkdown(raw) {
    if (!window.marked || !window.DOMPurify) return renderSource(raw, "markdown");
    const rendered = window.marked.parse(raw, { gfm: true });
    content.innerHTML = `<article class="repo-viewer-markdown">${window.DOMPurify.sanitize(rendered)}</article>`;
    content.querySelectorAll("pre code").forEach(node => window.hljs && window.hljs.highlightElement(node));
  }

  function renderJson(raw) {
    try {
      const value = JSON.parse(raw);
      content.innerHTML = `<div class="repo-viewer-json-tree">${jsonNode(value, null, 0)}</div>`;
    }
    catch (_) { renderSource(raw, "json"); }
  }

  function jsonNode(value, key, depth) {
    const keyHtml = key === null ? "" : `<span class="json-key${valuableKey.test(key) ? " is-valuable" : ""}">${escapeHtml(String(key))}</span><span class="json-colon">:</span> `;
    if (value === null) return `<div class="json-leaf">${keyHtml}<span class="json-null">null</span></div>`;
    if (typeof value !== "object") {
      const type = typeof value;
      const shown = type === "string" ? `&quot;${escapeHtml(value)}&quot;` : escapeHtml(String(value));
      return `<div class="json-leaf">${keyHtml}<span class="json-${type}">${shown}</span></div>`;
    }
    const entries = Array.isArray(value) ? value.map((item, index) => [index, item]) : Object.entries(value);
    const kind = Array.isArray(value) ? "array" : "object";
    const preview = jsonPreview(value, kind);
    const open = depth < 2 ? " open" : "";
    const children = entries.map(([childKey, childValue]) => jsonNode(childValue, childKey, depth + 1)).join("");
    return `<details class="json-branch json-${kind}"${open}><summary>${keyHtml}<span class="json-bracket">${kind === "array" ? "[" : "{"}</span><span class="json-preview">${escapeHtml(preview)}</span><span class="json-count">${entries.length} ${entries.length === 1 ? "item" : "items"}</span><span class="json-bracket">${kind === "array" ? "]" : "}"}</span></summary><div class="json-children">${children}</div></details>`;
  }

  function jsonPreview(value, kind) {
    if (!Array.isArray(value)) {
      const highlights = Object.entries(value).filter(([key, item]) => valuableKey.test(key) && (typeof item !== "object" || item === null)).slice(0, 2);
      if (highlights.length) return highlights.map(([key, item]) => `${key}: ${String(item).slice(0, 45)}`).join(" · ");
    }
    return kind === "array" ? "list" : "record";
  }

  function setJsonExpansion(open) {
    content.querySelectorAll("details.json-branch").forEach(node => { node.open = open; });
  }

  function setViewerWidth(width) {
    const min = 360;
    const max = Math.max(min, window.innerWidth - 360);
    const pixels = Math.min(max, Math.max(min, width));
    document.documentElement.style.setProperty("--repo-viewer-width", `${pixels}px`);
    localStorage.setItem("repo-viewer-width", String(pixels));
  }

  function beginResize(event) {
    if (window.innerWidth <= 1000) return;
    event.preventDefault();
    document.body.classList.add("repo-viewer-resizing");
    const move = moveEvent => setViewerWidth(window.innerWidth - moveEvent.clientX);
    const stop = () => {
      document.body.classList.remove("repo-viewer-resizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  }

  const savedWidth = Number(localStorage.getItem("repo-viewer-width"));
  if (savedWidth) setViewerWidth(savedWidth);
  resizer.addEventListener("pointerdown", beginResize);
  resizer.addEventListener("keydown", event => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const current = viewer.getBoundingClientRect().width;
    setViewerWidth(current + (event.key === "ArrowLeft" ? 24 : -24));
  });

  function renderCsv(raw) {
    if (!window.Papa) return renderSource(raw, "plaintext");
    const result = window.Papa.parse(raw, { skipEmptyLines: false });
    const rows = result.data.slice(0, 1000);
    const html = rows.map((row, rowIndex) => `<tr>${row.map(cell => `<${rowIndex ? "td" : "th"}>${escapeHtml(String(cell))}</${rowIndex ? "td" : "th"}>`).join("")}</tr>`).join("");
    content.innerHTML = `<div class="repo-viewer-table-wrap"><table class="repo-viewer-table">${html}</table>${result.data.length > 1000 ? "<p>Showing the first 1,000 rows.</p>" : ""}</div>`;
  }

  function toggleMarkdown() {
    state.mode = state.mode === "rendered" ? "source" : "rendered";
    toggle.textContent = state.mode === "rendered" ? "Source" : "Rendered";
    render(state.path, state.raw);
  }

  function findNext(wrapper) {
    const query = wrapper.querySelector(".repo-viewer-search").value;
    if (query) window.find(query, false, false, true, false, true, false);
  }

  document.addEventListener("click", event => {
    const anchor = event.target.closest("a[href]");
    if (!anchor || anchor.classList.contains("ide") || anchor.target === "_blank") return;
    if ((anchor.getAttribute("href") || "").startsWith("#")) return;
    const path = resolveRepositoryPath(anchor);
    if (!path) return;
    event.preventDefault();
    openPath(path);
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeViewer(); });
  fetch(location.pathname, { method: "HEAD" }).then(response => {
    state.root = response.headers.get("X-Repository-Root") || "";
    if (!state.root) return;
    document.querySelectorAll("a.ide[data-editor-path]").forEach(anchor => {
      anchor.href = `vscode://file${encodeURI(state.root)}/${encodeURI(anchor.dataset.editorPath)}`;
    });
  }).catch(() => {});
  if (location.hash.startsWith("#view=")) openPath(decodeURIComponent(location.hash.slice(6)));
})();
