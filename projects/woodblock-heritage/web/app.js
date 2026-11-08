"use strict";

const $ = (id) => document.getElementById(id);
const state = { source: null, work: null, regions: [] };

function newKey() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  return "k-" + Date.now() + "-" + Math.random().toString(16).slice(2);
}

function showError(error) {
  const box = $("error");
  if (!error) {
    box.hidden = true;
    box.textContent = "";
    return;
  }
  const data = error.data || {};
  const lines = [
    `${data.code || "ERROR"}: ${data.message || error.message || "请求失败"}`,
    data.cause ? `原因：${data.cause}` : "",
    data.fix ? `下一步：${data.fix}` : "",
    data.details ? `细节：${JSON.stringify(data.details)}` : "",
  ].filter(Boolean);
  box.textContent = lines.join("\n");
  box.hidden = false;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  let data = {};
  try { data = await response.json(); } catch (_) { /* non-JSON */ }
  if (!response.ok) {
    const error = new Error(data.message || `HTTP ${response.status}`);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function badge(text, cls) {
  const span = document.createElement("span");
  span.className = `badge ${cls || ""}`;
  span.textContent = text;
  return span;
}

function field(labelText, input) {
  const label = document.createElement("label");
  label.textContent = labelText;
  label.appendChild(input);
  return label;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("读取文件失败"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}

function renderSource(source) {
  state.source = source;
  const image = $("source-image");
  image.onload = () => drawRegions(state.regions);
  image.src = `/api/v1/heritage/sources/${encodeURIComponent(source.source_id)}/image?v=${encodeURIComponent(source.content_hash.slice(0, 8))}`;
  $("source-result").hidden = false;
  const meta = $("source-meta");
  meta.replaceChildren();
  const entries = [
    ["来源 ID", source.source_id],
    ["内容哈希", source.content_hash.slice(0, 16) + "…"],
    ["实际尺寸", `${source.width} × ${source.height}`],
    ["物理页序", source.physical_index == null ? "未知（null）" : String(source.physical_index)],
    ["印刷页码", source.printed_label || "未知"],
    ["许可", source.access_policy],
  ];
  for (const [key, value] of entries) {
    const dt = document.createElement("dt"); dt.textContent = key;
    const dd = document.createElement("dd"); dd.textContent = value;
    meta.append(dt, dd);
  }
}

function onCanvasClick(event) {
  const canvas = event.currentTarget;
  const info = $("region-info");
  const rect = canvas.getBoundingClientRect();
  if (!state.source || !rect.width || !rect.height) {
    info.textContent = "没有可命中的区域";
    return;
  }
  const x = (event.clientX - rect.left) / rect.width;
  const y = (event.clientY - rect.top) / rect.height;
  const region = state.regions.find((item) => item.source_id === state.source.source_id
    && x >= item.bbox[0] && x <= item.bbox[2] && y >= item.bbox[1] && y <= item.bbox[3]);
  if (!region) {
    info.textContent = `未命中区域（归一化 ${x.toFixed(3)}, ${y.toFixed(3)}）`;
    return;
  }
  const text = region.text ? `：${region.text.slice(0, 80)}` : "";
  info.textContent = `命中 ${region.id}（${region.kind}）${text}`;
}

function drawRegions(regions) {
  const image = $("source-image");
  const canvas = $("region-canvas");
  if (!canvas.dataset.bound) {
    canvas.addEventListener("click", onCanvasClick);
    canvas.dataset.bound = "1";
  }
  if (!regions || !image.complete || !image.naturalWidth) {
    canvas.width = 0; canvas.height = 0;
    return;
  }
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  const sourceId = state.source && state.source.source_id;
  for (const region of regions) {
    if (region.source_id !== sourceId) continue;
    const [x0, y0, x1, y1] = region.bbox;
    const x = x0 * canvas.width;
    const y = y0 * canvas.height;
    const width = (x1 - x0) * canvas.width;
    const height = (y1 - y0) * canvas.height;
    context.lineWidth = Math.max(2, canvas.width / 300);
    context.strokeStyle = region.kind === "text" ? "#a63c2e" : "#3f6b5a";
    context.strokeRect(x, y, width, height);
    context.font = `${Math.max(12, Math.round(canvas.width / 45))}px sans-serif`;
    context.fillStyle = region.kind === "text" ? "#a63c2e" : "#3f6b5a";
    context.fillText(region.id, x + 4, Math.max(14, y + 16));
  }
}

async function loadSource(sourceId) {
  if (state.source && state.source.source_id === sourceId) return state.source;
  const source = await api(`/api/v1/heritage/sources/${encodeURIComponent(sourceId)}`);
  renderSource(source);
  return source;
}

function sampleWork(sourceId) {
  return {
    schema_version: "heritage-review-v1",
    source_ids: [sourceId],
    regions: [
      { id: "r-title", source_id: sourceId, kind: "text", bbox: [0.05, 0.05, 0.7, 0.15],
        coordinate_system: "normalized", text: "合成门神示例", text_kind: "exact" },
      { id: "r-image", source_id: sourceId, kind: "image", bbox: [0.1, 0.2, 0.9, 0.95],
        coordinate_system: "normalized" },
    ],
    claims: [
      { id: "c-title", predicate: "source_title",
        object: { kind: "literal", value: "合成门神示例" }, evidence_refs: ["r-title"] },
      { id: "c-category", predicate: "source_category",
        object: { kind: "literal", value: "门神" }, evidence_refs: ["r-title"] },
    ],
    issues: [
      { code: "PAIR_SCOPE_AMBIGUOUS", message: "合成示例：标题与图幅范围需人工确认",
        evidence_refs: ["r-title", "r-image"] },
    ],
  };
}

async function loadWorks() {
  const list = $("work-list");
  list.replaceChildren();
  try {
    const data = await api("/api/v1/heritage/works");
    if (!data.items.length) {
      const li = document.createElement("li");
      li.textContent = "还没有候选。先登记来源并导入。";
      list.appendChild(li);
      return;
    }
    for (const item of data.items) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = `${item.title || "无题名"} · v${item.current_version}`;
      button.addEventListener("click", () => selectWork(item.work_id));
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${item.work_id} · ${item.claim_count} 条断言 · ${item.issue_count} 个问题`;
      li.append(button, meta);
      list.appendChild(li);
    }
  } catch (error) {
    showError(error);
  }
}

function claimCard(claim) {
  const card = document.createElement("div");
  card.className = "claim";
  card.dataset.claim = claim.id;
  const head = document.createElement("div");
  head.append(
    badge(claim.id, ""),
    document.createTextNode(" "),
    badge(claim.predicate, ""),
    document.createTextNode(" "),
    badge(`validation:${claim.validation_status}`, claim.validation_status),
    document.createTextNode(" "),
    badge(`support:${claim.support_status}`, claim.support_status),
    document.createTextNode(" "),
    badge(`review:${claim.review_status}`, claim.review_status),
  );
  const value = document.createElement("div");
  value.textContent = (claim.object && claim.object.value != null) ? claim.object.value : "（空值）";
  value.className = "claim-value";
  const refs = document.createElement("div");
  refs.className = "issue-meta";
  refs.textContent = `证据：${claim.evidence_refs.join("、") || "无"}`;
  const actions = document.createElement("div");
  actions.className = "claim-actions";
  const action = document.createElement("select");
  action.className = "action";
  for (const [valueName, label] of [["none", "不裁决"], ["approve", "批准"], ["reject", "驳回"], ["revise", "修订"]]) {
    const option = document.createElement("option");
    option.value = valueName; option.textContent = label;
    action.appendChild(option);
  }
  const support = document.createElement("select");
  support.className = "support";
  for (const valueName of ["supported", "disputed", "insufficient"]) {
    const option = document.createElement("option");
    option.value = valueName; option.textContent = valueName;
    support.appendChild(option);
  }
  actions.append(action, support);
  const revise = document.createElement("div");
  revise.className = "revise-fields";
  revise.hidden = true;
  const predicate = document.createElement("input");
  predicate.className = "revise-predicate"; predicate.placeholder = "新谓词";
  const literal = document.createElement("input");
  literal.className = "revise-value"; literal.placeholder = "新字面值";
  const evidence = document.createElement("input");
  evidence.className = "revise-evidence"; evidence.placeholder = "证据 id，逗号分隔";
  revise.append(predicate, literal, evidence);
  action.addEventListener("change", () => { revise.hidden = action.value !== "revise"; });
  card.append(head, value, refs, actions, revise);
  return card;
}

function setReviewEnabled(enabled) {
  $("submit-review").disabled = !enabled;
  $("publish").disabled = !enabled;
  document.querySelectorAll("#claims select, #claims input, #issues input").forEach((element) => {
    element.disabled = !enabled;
  });
}

function renderWork(work) {
  state.work = work;
  const payload = work.payload;
  state.regions = payload.regions || [];
  $("work-empty").hidden = true;
  $("work-detail").hidden = false;
  const header = $("work-header");
  header.replaceChildren();
  const title = document.createElement("h3");
  const titleClaim = (payload.claims || []).find((claim) => claim.predicate === "source_title");
  title.textContent = (titleClaim && titleClaim.object && titleClaim.object.value) || "无题名候选";
  const meta = document.createElement("p");
  meta.className = "hint";
  meta.textContent = `${work.work_id} · 当前 v${work.current_version} · 查看 v${work.version}${work.historical ? "（历史·只读）" : ""} · 导入版本 ${payload.import_version}`;
  const versionSelect = document.createElement("select");
  versionSelect.id = "version-select";
  for (let version = work.current_version; version >= 1; version -= 1) {
    const option = document.createElement("option");
    option.value = String(version);
    option.textContent = `查看 v${version}`;
    versionSelect.appendChild(option);
  }
  versionSelect.value = String(work.version);
  versionSelect.addEventListener("change", () => {
    selectWork(work.work_id, Number(versionSelect.value));
  });
  header.append(title, meta, versionSelect);

  const claims = $("claims");
  claims.replaceChildren();
  if (!(payload.claims || []).length) {
    claims.textContent = "没有断言。";
  } else {
    for (const claim of payload.claims) claims.appendChild(claimCard(claim));
  }

  const issues = $("issues");
  issues.replaceChildren();
  for (const issue of payload.issues || []) {
    const li = document.createElement("li");
    if (issue.status === "resolved") li.className = "resolved";
    const label = document.createElement("label");
    if (issue.status !== "resolved") {
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "issue-resolve";
      checkbox.value = issue.id;
      label.appendChild(checkbox);
    }
    const text = document.createElement("span");
    text.textContent = `${issue.code}：${issue.message}${issue.blocking ? "（阻断）" : ""}`;
    label.appendChild(text);
    li.appendChild(label);
    if (issue.reason) {
      const reason = document.createElement("div");
      reason.className = "issue-meta";
      reason.textContent = `处置：${issue.reason}`;
      li.appendChild(reason);
    }
    issues.appendChild(li);
  }
  if (!(payload.issues || []).length) {
    const li = document.createElement("li"); li.textContent = "没有未决问题。"; issues.appendChild(li);
  }

  const events = $("events");
  events.replaceChildren();
  for (const event of work.events || []) {
    const li = document.createElement("li");
    li.textContent = `v${event.from_version} → v${event.to_version} · ${event.reviewer} · ${event.reason}`;
    events.appendChild(li);
  }
  if (!(work.events || []).length) {
    const li = document.createElement("li"); li.textContent = "尚无审核事件。"; events.appendChild(li);
  }
  setReviewEnabled(!work.historical);
  loadPublicationHistory(work.work_id);
  drawRegions(state.regions);
}

async function selectWork(workId, version = null) {
  clearError();
  try {
    const suffix = version ? `?version=${encodeURIComponent(version)}` : "";
    const work = await api(`/api/v1/heritage/works/${encodeURIComponent(workId)}${suffix}`);
    const sourceId = work.payload.source_ids && work.payload.source_ids[0];
    if (sourceId) await loadSource(sourceId);
    renderWork(work);
  } catch (error) {
    showError(error);
  }
}

function collectReview() {
  const decisions = [];
  const cards = $("claims").querySelectorAll(".claim");
  for (const card of cards) {
    const action = card.querySelector(".action").value;
    if (action === "none") continue;
    const decision = { claim_id: card.dataset.claim, action };
    if (action === "approve") {
      decision.support_status = card.querySelector(".support").value;
    }
    if (action === "revise") {
      const predicate = card.querySelector(".revise-predicate").value.trim();
      const value = card.querySelector(".revise-value").value;
      const evidence = card.querySelector(".revise-evidence").value.trim();
      if (predicate) decision.predicate = predicate;
      if (value !== "") decision.object = { kind: "literal", value };
      if (evidence) decision.evidence_refs = evidence.split(",").map((item) => item.trim()).filter(Boolean);
    }
    decisions.push(decision);
  }
  const resolutions = [];
  for (const checkbox of $("issues").querySelectorAll(".issue-resolve:checked")) {
    resolutions.push({ issue_id: checkbox.value, reason: $("review-reason").value.trim() || "本地审核处置" });
  }
  return { decisions, resolutions };
}

async function submitReview() {
  clearError();
  const work = state.work;
  if (!work) return;
  if (work.historical) {
    showError({ message: "历史版本只读；请切换到当前版本后再审核" });
    return;
  }
  const { decisions, resolutions } = collectReview();
  if (!decisions.length && !resolutions.length) {
    showError({ message: "没有选择任何裁决或问题处置" });
    return;
  }
  const reason = $("review-reason").value.trim();
  if (!reason) {
    showError({ message: "请填写审核/发布理由" });
    return;
  }
  const button = $("submit-review");
  button.disabled = true;
  try {
    const response = await api(`/api/v1/heritage/works/${encodeURIComponent(work.work_id)}/reviews`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": newKey() },
      body: JSON.stringify({
        expected_version: work.current_version,
        reviewer: $("reviewer").value.trim() || "local-reviewer",
        reason,
        decisions,
        issue_resolutions: resolutions,
      }),
    });
    renderWork(response.work);
    $("review-reason").value = "";
    await loadWorks();
    await refreshKnowledge();
  } catch (error) {
    showError(error);
    if (error.status === 409) await selectWork(work.work_id);
  } finally {
    button.disabled = false;
  }
}

async function publish() {
  clearError();
  const work = state.work;
  if (!work) return;
  if (work.historical) {
    showError({ message: "历史版本不能发布；请切换到当前版本" });
    return;
  }
  const reason = $("review-reason").value.trim();
  if (!reason) {
    showError({ message: "发布前请填写理由" });
    return;
  }
  const button = $("publish");
  button.disabled = true;
  try {
    const publication = await api("/api/v1/heritage/publications", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": newKey() },
      body: JSON.stringify({ work_id: work.work_id, expected_version: work.current_version }),
    });
    showError(null);
    const mark = document.createElement("p");
    mark.className = "hint";
    mark.textContent = `已发布 ${publication.publication_id}（v${publication.version}，${publication.claims.length} 条合格断言）`;
    $("work-header").appendChild(mark);
    await refreshKnowledge();
    await loadPublicationHistory(work.work_id);
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
}

async function loadPublicationHistory(workId) {
  const box = $("publication-history");
  box.replaceChildren();
  try {
    const data = await api(`/api/v1/heritage/works/${encodeURIComponent(workId)}/publications`);
    if (state.work && state.work.work_id !== workId) return;
    if (!data.items.length) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "这个作品还没有发布过快照。";
      box.appendChild(p);
      return;
    }
    for (const item of data.items) {
      const article = document.createElement("article");
      const title = document.createElement("h3");
      title.textContent = `v${item.version} · ${item.publication_id}`;
      const meta = document.createElement("p");
      meta.className = "hint";
      meta.textContent = item.historical ? "历史快照（不是当前知识）" : "当前发布版本";
      const list = document.createElement("ul");
      for (const claim of item.claims) {
        const li = document.createElement("li");
        li.textContent = `${claim.predicate} = ${claim.object && claim.object.value}`;
        list.appendChild(li);
      }
      article.append(title, meta, list);
      box.appendChild(article);
    }
  } catch (error) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = `发布历史加载失败：${error.message}`;
    box.appendChild(p);
  }
}

async function refreshKnowledge() {
  try {
    const data = await api("/api/v1/heritage/knowledge");
    const box = $("knowledge");
    box.replaceChildren();
    if (!data.items.length) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "当前没有已发布且未过期的知识。";
      box.appendChild(p);
      return;
    }
    for (const item of data.items) {
      const article = document.createElement("article");
      const title = document.createElement("h3");
      const titleClaim = item.claims.find((claim) => claim.predicate === "source_title");
      title.textContent = (titleClaim && titleClaim.object && titleClaim.object.value) || item.work_id;
      const meta = document.createElement("p");
      meta.className = "hint";
      meta.textContent = `${item.publication_id} · 作品 v${item.version} · ${item.claims.length} 条`;
      const list = document.createElement("ul");
      for (const claim of item.claims) {
        const li = document.createElement("li");
        li.textContent = `${claim.predicate} = ${claim.object && claim.object.value}`;
        list.appendChild(li);
      }
      article.append(title, meta, list);
      box.appendChild(article);
    }
  } catch (error) {
    showError(error);
  }
}

function clearError() { showError(null); }

$("source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  const file = $("source-file").files[0];
  if (!file) { showError({ message: "请选择图片" }); return; }
  const button = event.submitter;
  if (button) button.disabled = true;
  try {
    const body = {
      filename: file.name,
      source_note: $("source-note").value.trim(),
      access_policy: $("access-policy").value.trim(),
      physical_index: $("physical-index").value ? Number($("physical-index").value) : null,
      printed_label: $("printed-label").value.trim() || null,
      image_base64: await fileToBase64(file),
    };
    const source = await api("/api/v1/heritage/sources", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    renderSource(source);
    $("work-json").value = JSON.stringify(sampleWork(source.source_id), null, 2);
  } catch (error) {
    showError(error);
  } finally {
    if (button) button.disabled = false;
  }
});

$("make-sample").addEventListener("click", () => {
  if (!state.source) { showError({ message: "先登记来源" }); return; }
  $("work-json").value = JSON.stringify(sampleWork(state.source.source_id), null, 2);
});

$("import-work").addEventListener("click", async () => {
  clearError();
  const button = $("import-work");
  button.disabled = true;
  try {
    let body;
    try { body = JSON.parse($("work-json").value); }
    catch (error) { showError({ message: "候选 JSON 不合法", cause: error.message }); return; }
    const work = await api("/api/v1/heritage/works", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": newKey() },
      body: JSON.stringify(body),
    });
    renderWork(work);
    await loadWorks();
  } catch (error) {
    showError(error);
  } finally {
    button.disabled = false;
  }
});

$("submit-review").addEventListener("click", submitReview);
$("publish").addEventListener("click", publish);
$("refresh-knowledge").addEventListener("click", refreshKnowledge);

loadWorks();
refreshKnowledge();
