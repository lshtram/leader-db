(function () {
  "use strict";

  const state = { data: null, rows: [], sortByMse: false, selected: null };
  const head = document.getElementById("table-head");
  const body = document.getElementById("table-body");
  const record = document.getElementById("record");
  const filter = document.getElementById("filter");
  const sortButton = document.getElementById("sort-mse");

  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);
  const fmt = value => value == null ? "—" : Number(value).toFixed(Number(value) % 1 ? 1 : 0);
  const score = (value, kind) => `<span class="score ${value == null ? "score-null" : `score-${kind}`}">${fmt(value)}</span>`;
  const prose = value => esc(value).split(/\n\s*\n/).map(paragraph => `<p>${paragraph}</p>`).join("");
  const safeUrl = value => {
    try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : null; }
    catch (_) { return null; }
  };

  function renderHeader() {
    head.innerHTML = `<th scope="col">Ruler</th>${Object.entries(state.data.chapter_titles).map(([id, title]) => `<th scope="col" title="${esc(title)}">${esc(id)}<br>${esc(title.split(" ")[0])}</th>`).join("")}<th scope="col">Agreement<br>MSE ↓</th>`;
  }

  function renderRows() {
    const query = filter.value.trim().toLowerCase();
    let rows = state.data.rulers.filter(row => `${row.ruler_name} ${row.country_name} ${row.iso3}`.toLowerCase().includes(query));
    if (state.sortByMse) rows = [...rows].sort((a, b) => (b.mse ?? -1) - (a.mse ?? -1));
    state.rows = rows;
    body.innerHTML = rows.map(row => `<tr data-iso3="${esc(row.iso3)}">
      <th scope="row"><span class="ruler-name">${esc(row.ruler_name)}</span><span class="country-name">${esc(row.country_name)} · ${esc(row.iso3)}${row.source_run === "repair" ? " · repaired" : ""}</span></th>
      ${Object.keys(state.data.chapter_titles).map(chapter => `<td><button class="score-button" type="button" data-iso3="${esc(row.iso3)}" data-chapter="${esc(chapter)}" aria-label="Open ${esc(row.ruler_name)} ${esc(chapter)} record"><span class="score-pair">${score(row.automated_scores[chapter], "auto")}${score(row.client_scores[chapter], "client")}</span></button></td>`).join("")}
      <td class="mse">${row.mse == null ? "—" : row.mse.toFixed(3)}<small>${row.comparable_chapters}/8 cells</small></td>
    </tr>`).join("");
  }

  function evidenceCard(item) {
    const url = safeUrl(item.url);
    const title = item.title || item.publisher || item.evidence_id;
    const source = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>` : esc(title);
    return `<article class="evidence"><strong>${esc(item.evidence_id)} · ${source}</strong><p>${esc(item.claim || item.excerpt || "No claim summary recorded.")}</p><div class="source">${esc(item.publisher || "Unknown publisher")}${item.publication_date ? ` · ${esc(item.publication_date)}` : ""}${item.source_locator ? ` · ${esc(item.source_locator)}` : ""}</div></article>`;
  }

  function lensHtml(lens, evidenceById) {
    const evidence = lens.evidence_ids.map(id => evidenceById[id]).filter(Boolean);
    return `<section class="lens"><h4>${esc(lens.methodology_id)} · ${esc(lens.question)}</h4><div class="lens-meta"><span class="status">${esc(lens.status.replaceAll("_", " "))}</span><span class="status">${evidence.length} source claim${evidence.length === 1 ? "" : "s"}</span></div><p>${esc(lens.write_up)}</p>${evidence.length ? `<div class="evidence-list">${evidence.map(evidenceCard).join("")}</div>` : `<p class="warning">No lens-specific evidence item was retained. This is not scored as zero.</p>`}</section>`;
  }

  function evidenceReference(item) {
    return `<li><b>${esc(item.evidence_id)}</b> — ${esc(item.explanation)}</li>`;
  }

  function recoveryHtml(recovery) {
    if (!recovery) return "";
    const weak = recovery.missing_or_weak_lenses || [];
    const status = recovery.status === "pending_corrected_flow_review"
      ? "Pending corrected-flow review"
      : "Substantive review required";
    return `<section class="recovery"><h3>${esc(status)}</h3><p>This null is provisional and is not a zero. The corrected workflow will first preserve and remap the existing research record, then request targeted research only if a material gap remains.</p><dl><div><dt>Currently retained</dt><dd>${esc(recovery.current_evidence_count)} chapter evidence item${recovery.current_evidence_count === 1 ? "" : "s"}</dd></div><div><dt>Weak lenses</dt><dd>${weak.length ? esc(weak.join(", ")) : "Not specified"}</dd></div><div><dt>Requested follow-up</dt><dd>${esc(recovery.requested_follow_up || "Substantive review of the existing record")}</dd></div><div><dt>Research limit</dt><dd>${recovery.maximum_targeted_rounds ? `Up to ${esc(recovery.maximum_targeted_rounds)} targeted rounds` : "No automatic research round"}</dd></div></dl></section>`;
  }

  function judgeHtml(judge, recovery) {
    if (!judge) return `<section class="judge"><h3>Judge synthesis</h3><p class="warning">No validated chapter judgment is available for this ruler and chapter.</p></section>`;
    const range = judge.plausible_score_range ? `${fmt(judge.plausible_score_range.lower)}–${fmt(judge.plausible_score_range.upper)}` : "—";
    const positives = (judge.decisive_positive_evidence || []).map(evidenceReference).join("");
    const negatives = (judge.decisive_negative_evidence || []).map(evidenceReference).join("");
    return `${recoveryHtml(recovery)}<section class="judge"><h3>How the judge reached the score</h3><div class="judge-grid"><div><span>Automated score</span><strong>${fmt(judge.score_1_to_10)}</strong></div><div><span>Confidence</span><strong>${fmt(judge.confidence_score)}</strong></div><div><span>Plausible range</span><strong>${range}</strong></div></div>
      ${judge.reader_abstract ? `<div class="judge-abstract">${prose(judge.reader_abstract)}</div>` : judge.chapter_rationale ? `<p>${esc(judge.chapter_rationale)}</p>` : ""}
      ${judge.insufficient_evidence_reason ? `<p class="warning"><b>Why no score:</b> ${esc(judge.insufficient_evidence_reason)}</p>` : ""}
      ${positives ? `<h4>Decisive positive evidence</h4><ul>${positives}</ul>` : ""}
      ${negatives ? `<h4>Decisive negative evidence</h4><ul>${negatives}</ul>` : ""}
      ${judge.inherited_baseline_and_constraints ? `<h4>Inherited baseline and constraints</h4><p>${esc(judge.inherited_baseline_and_constraints)}</p>` : ""}
      ${judge.ruler_attribution ? `<h4>Ruler attribution</h4><p>${esc(judge.ruler_attribution)}</p>` : ""}
      ${judge.lower_anchor_rejected ? `<h4>Calibration</h4><p>${esc(judge.lower_anchor_rejected)} ${esc(judge.higher_anchor_rejected || "")}</p>` : ""}
      ${judge.manual_review_required ? `<p class="warning"><b>Manual review:</b> ${esc(judge.manual_review_reason || "Required")}</p>` : ""}
      ${judge.viewer_normalization_note ? `<p class="warning">${esc(judge.viewer_normalization_note)}</p>` : ""}
    </section>`;
  }

  function chapterHtml(row, chapter, selectedChapter) {
    const evidenceById = Object.fromEntries(chapter.evidence.map(item => [item.evidence_id, item]));
    const auto = row.automated_scores[chapter.chapter_id];
    const client = row.client_scores[chapter.chapter_id];
    return `<details class="chapter" data-chapter="${esc(chapter.chapter_id)}"${chapter.chapter_id === selectedChapter ? " open" : ""}><summary><span class="chapter-code">${esc(chapter.chapter_id)}</span><span><span class="chapter-title">${esc(chapter.title)}</span><span class="chapter-scoreline">Automated ${fmt(auto)} · Client ${fmt(client)}${chapter.recovery ? " · pending review" : ""}${auto != null && client != null ? ` · squared error ${((auto-client) ** 2).toFixed(2)}` : ""}</span></span></summary><div class="chapter-body">${chapter.lenses.map(lens => lensHtml(lens, evidenceById)).join("")}${judgeHtml(chapter.judge, chapter.recovery)}</div></details>`;
  }

  function renderRecord(iso3, selectedChapter) {
    const row = state.data.rulers.find(item => item.iso3 === iso3);
    if (!row) return;
    state.selected = { iso3, selectedChapter };
    record.classList.remove("empty");
    record.innerHTML = `<header class="record-header"><div><p class="eyebrow">Complete ruler record · ${esc(row.source_run)} dossier</p><h2>${esc(row.ruler_name)}</h2><p>${esc(row.country_name)} · ${esc(row.iso3)} · ${state.data.target_year} · dossier ${esc(row.ruler_year_id)}</p></div><div class="record-mse"><span>Mean squared error</span><strong>${row.mse == null ? "—" : row.mse.toFixed(3)}</strong><span>${row.comparable_chapters} comparable chapters</span></div></header><div class="chapter-list">${row.chapters.map(chapter => chapterHtml(row, chapter, selectedChapter)).join("")}</div>`;
    record.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  body.addEventListener("click", event => {
    const button = event.target.closest(".score-button");
    if (button) renderRecord(button.dataset.iso3, button.dataset.chapter);
  });
  filter.addEventListener("input", renderRows);
  sortButton.addEventListener("click", () => {
    state.sortByMse = !state.sortByMse;
    sortButton.textContent = state.sortByMse ? "Restore cohort order" : "Sort by MSE";
    renderRows();
  });

  fetch("data.json").then(response => {
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }).then(data => {
    state.data = data;
    document.getElementById("ruler-count").textContent = data.rulers.length;
    document.getElementById("cell-count").textContent = data.overall_comparable_cells;
    document.getElementById("overall-mse").textContent = data.overall_mse.toFixed(3);
    document.getElementById("method-note").textContent = data.method_note;
    document.getElementById("methodology-update").textContent = data.methodology_update;
    renderHeader();
    renderRows();
  }).catch(error => {
    record.innerHTML = `<div class="empty-state"><h2>Unable to load viewer data</h2><p>${esc(error)}</p><p>Serve this page through <code>python scripts/serve_design_reviews.py --page docs/client-results/2023-top20/index.html</code>.</p></div>`;
  });
})();
