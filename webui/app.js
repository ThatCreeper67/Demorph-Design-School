"use strict";

const $ = (selector) => document.querySelector(selector);
const state = { file: null, previewUrl: null, dims: null, analysisId: null, polling: false, pollTimer: null, busy: false, history: [] };
const stages = {
  queued: "Queued for local analysisâ€¦",
  checking_model: "Checking the required Ollama modelâ€¦",
  preparing_visual_input: "Preparing the original image inputâ€¦",
  applying_curriculum: "Retrieving relevant design curriculumâ€¦",
  analyzing_with_qwen: "Qwen is analyzing the design. This can take a few minutesâ€¦",
  validating_analysis: "Checking evidence and result referencesâ€¦",
  saving_result: "Saving this analysis to local historyâ€¦",
  cancel_requested: "Cancellation requested. Waiting for the active model callâ€¦",
  cancelled: "Analysis cancelled; the result was discarded.",
  complete: "Analysis complete",
  partial: "Analysis finished with limitations",
  failed: "Analysis failed",
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const type = response.headers.get("content-type") || "";
  if (!response.ok) {
    const payload = type.includes("application/json") ? await response.json() : { message: `Request failed (${response.status}).` };
    const error = new Error(payload.message || `Request failed (${response.status}).`);
    error.code = payload.error;
    error.status = response.status;
    throw error;
  }
  return type.includes("application/json") ? response.json() : response;
}

function setHealth(data) {
  const pill = $("#healthPill");
  const text = $("#healthText");
  pill.classList.toggle("ready", Boolean(data.model_available));
  pill.classList.toggle("failed", !data.model_available);
  text.textContent = data.model_available ? "Ollama ready" : "Ollama unavailable";
  $("#uploadLimit").textContent = String(data.upload_limit_mb || 25);
  pill.title = data.model_available ? `${data.model} is available locally.` : data.message || `Required model: ${data.model}`;
}

async function checkHealth() {
  try { setHealth(await api("/api/health")); }
  catch { setHealth({ model_available: false, message: "Local API unavailable." }); }
}

function showState(name) {
  for (const id of ["welcomeState", "progressState", "errorState", "resultState"]) $("#" + id).classList.toggle("hidden", id !== name);
}

function readableSize(bytes) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function clearUploadError() {
  $("#uploadError").classList.add("hidden");
  $("#uploadError").textContent = "";
}

function uploadError(message) {
  const node = $("#uploadError");
  node.textContent = message;
  node.classList.remove("hidden");
}

function setBusy(value) {
  state.busy = value;
  $("#analyzeBtn").disabled = value || !state.file;
  $("#fileInput").disabled = value;
  $("#removeImageBtn").disabled = value;
  $("#briefInput").disabled = value;
  $("#cancelBtn").classList.toggle("hidden", !value);
  $("#newAnalysisBtn").disabled = value;
  $("#navNew").disabled = value;
}

function resetUpload() {
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.file = null; state.previewUrl = null; state.dims = null;
  $("#fileInput").value = "";
  $("#emptyUpload").classList.remove("hidden");
  $("#previewWrap").classList.add("hidden");
  $("#fileInfo").classList.add("hidden");
  $("#removeImageBtn").classList.add("hidden");
  $("#imagePreview").removeAttribute("src");
  $("#analyzeBtn").disabled = true;
  clearUploadError();
}

function chooseFile(file) {
  if (!file || state.busy) return;
  clearUploadError();
  const extension = file.name.split(".").pop().toLowerCase();
  const supported = new Set(["image/png", "image/jpeg", "image/webp"]);
  const maxBytes = Number($("#uploadLimit").textContent || 25) * 1024 * 1024;
  if (!supported.has(file.type) && !["png", "jpg", "jpeg", "webp"].includes(extension)) { resetUpload(); uploadError("Choose a PNG, JPG, or WEBP image."); return; }
  if (file.size > maxBytes) { resetUpload(); uploadError(`Choose an image smaller than ${$("#uploadLimit").textContent} MB.`); return; }
  const url = URL.createObjectURL(file);
  const probe = new Image();
  probe.onload = () => {
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.file = file; state.previewUrl = url; state.dims = [probe.naturalWidth, probe.naturalHeight];
    $("#imagePreview").src = url;
    $("#emptyUpload").classList.add("hidden");
    $("#previewWrap").classList.remove("hidden");
    $("#fileInfo").classList.remove("hidden");
    $("#removeImageBtn").classList.remove("hidden");
    $("#fileName").textContent = file.name;
    $("#fileMeta").textContent = `${probe.naturalWidth} Ã— ${probe.naturalHeight} Â· ${readableSize(file.size)}`;
    $("#analyzeBtn").disabled = state.busy;
    clearUploadError();
  };
  probe.onerror = () => { URL.revokeObjectURL(url); resetUpload(); uploadError("This image could not be previewed. The file may be damaged."); };
  probe.src = url;
}

function resetWorkspace() {
  if (state.busy) return;
  state.analysisId = null;
  $("#briefInput").value = "";
  resetUpload();
  showState("welcomeState");
  $("#navNew").classList.add("selected");
  for (const button of document.querySelectorAll(".history-item")) button.classList.remove("active");
}

function setProgress(stage) {
  $("#progressTitle").textContent = stages[stage] || "Working on your analysisâ€¦";
  $("#progressDetail").textContent = stage === "analyzing_with_qwen"
    ? "One local Qwen analysis is evaluating evidence, relationships, hierarchy, and relevant specialist lenses. No percentage is estimated."
    : "The status reflects the current backend stage.";
  $("#cancelHint").classList.toggle("hidden", stage !== "cancel_requested");
}

async function startAnalysis() {
  if (!state.file || state.busy) return;
  clearUploadError();
  setBusy(true); showState("progressState"); setProgress("queued");
  const form = new FormData();
  form.append("image", state.file, state.file.name);
  form.append("brief", $("#briefInput").value.trim());
  try {
    const response = await api("/api/analyze", { method: "POST", body: form });
    state.analysisId = response.analysis_id;
    setProgress(response.stage);
    state.polling = true;
    state.pollTimer = setInterval(() => pollStatus(), 1200);
    await pollStatus();
  } catch (error) {
    setBusy(false);
    $("#errorTitle").textContent = error.status === 409 ? "An analysis is already running." : "Image upload failed.";
    $("#errorMessage").textContent = error.message;
    $("#retryBtn").classList.toggle("hidden", error.status === 409);
    showState("errorState");
  } finally {
    if (!state.polling && state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  }
}

async function pollStatus() {
  if (!state.analysisId || !state.polling) return;
  try {
    const job = await api(`/api/jobs/${state.analysisId}`);
    setProgress(job.stage);
    if (["complete", "partial"].includes(job.status)) {
      state.polling = false; if (state.pollTimer) clearInterval(state.pollTimer); state.pollTimer = null; setBusy(false);
      await openResult(state.analysisId);
      refreshHistory();
    } else if (["failed", "cancelled"].includes(job.status)) {
      state.polling = false; if (state.pollTimer) clearInterval(state.pollTimer); state.pollTimer = null; setBusy(false);
      $("#errorTitle").textContent = job.status === "cancelled" ? "Analysis cancelled." : "Analysis could not be completed.";
      $("#errorMessage").textContent = job.error_message || stages[job.stage] || "No result was saved as complete.";
      $("#retryBtn").classList.toggle("hidden", job.status === "cancelled");
      showState("errorState"); refreshHistory();
    } else if (job.status === "cancel_requested") {
      $("#cancelBtn").classList.add("hidden");
      $("#cancelHint").classList.remove("hidden");
    }
  } catch (error) {
    state.polling = false; if (state.pollTimer) clearInterval(state.pollTimer); state.pollTimer = null; setBusy(false);
    $("#errorTitle").textContent = "The local service connection was lost.";
    $("#errorMessage").textContent = error.message;
    $("#retryBtn").classList.add("hidden"); showState("errorState");
  }
}

async function cancelAnalysis() {
  if (!state.analysisId) return;
  try {
    await api(`/api/jobs/${state.analysisId}/cancel`, { method: "POST" });
    $("#cancelBtn").classList.add("hidden");
    $("#cancelHint").classList.remove("hidden");
    $("#progressTitle").textContent = stages.cancel_requested;
  } catch (error) { $("#progressDetail").textContent = error.message; }
}

function addEvidenceDetails(parent, refs, evidenceById) {
  const items = (refs || []).map((id) => evidenceById.get(id)).filter(Boolean);
  if (!items.length) return;
  const details = el("details", "evidence-details");
  details.append(el("summary", "", `Evidence Â· ${items.length}`));
  const list = el("ul", "evidence-list");
  for (const item of items) {
    const li = el("li");
    li.append(el("strong", "", `${item.evidence_id}${item.location ? ` Â· ${item.location}` : ""}: `));
    li.append(document.createTextNode(item.description));
    list.append(li);
  }
  details.append(list); parent.append(details);
}

function findingCard(title, body, { badge = "", impact = "", why = "", refs = [], evidenceById = new Map() } = {}) {
  const card = el("article", "finding-card");
  const top = el("div", "finding-top");
  top.append(el("h4", "", title));
  if (badge) top.append(el("span", `pill ${badge.toLowerCase()}`, badge));
  card.append(top);
  if (body) card.append(el("p", "", body));
  if (why && why !== body) card.append(el("p", "", `Why it matters: ${why}`));
  if (impact) card.append(el("p", "impact", `Likely impact: ${impact}`));
  addEvidenceDetails(card, refs, evidenceById);
  return card;
}

function addSection(parent, symbol, title, cards, extraClass = "") {
  if (!cards || !cards.length) return;
  const panel = el("section", `panel result-section ${extraClass}`);
  const heading = el("h3", "section-heading");
  heading.append(el("span", "section-mark", symbol), document.createTextNode(title));
  panel.append(heading);
  const list = el("div", "finding-list");
  for (const card of cards) list.append(card);
  panel.append(list); parent.append(panel);
}

function renderResult(record) {
  const result = record.result;
  const root = $("#resultState"); root.replaceChildren(); root.classList.remove("hidden");
  const header = el("div", "panel result-header");
  const title = el("div", "result-title");
  title.append(el("p", "eyebrow", record.status === "partial" ? "PARTIAL ANALYSIS Â· REVIEW LIMITATIONS" : "ANALYSIS Â· UNREVIEWED"), el("h2", "", record.source_filename));
  const actions = el("div", "result-actions");
  for (const [ext, label] of [["json", "Export JSON"], ["md", "Export Markdown"]]) {
    const link = el("a", "export-link", label); link.href = `/api/export/${record.analysis_id}.${ext}`; link.download = ""; actions.append(link);
  }
  const newButton = el("button", "text-button", "New analysis"); newButton.type = "button"; newButton.addEventListener("click", resetWorkspace); actions.append(newButton);
  header.append(title, actions); root.append(header);

  const strip = el("div", "panel image-strip");
  const thumb = el("img"); thumb.src = record.image_url; thumb.alt = "Analyzed design";
  const meta = el("div", "image-meta");
  meta.append(el("strong", "", `${record.width} Ã— ${record.height} px`), document.createTextNode(`${readableSize(record.size_bytes)} Â· ${new Date(record.created_at).toLocaleString()}`));
  strip.append(thumb, meta); root.append(strip);

  const evidenceById = new Map((result.evidence || []).map((item) => [item.evidence_id, item]));
  const obsById = new Map((result.observations || []).map((item) => [item.observation_id, item]));
  const relById = new Map((result.relationships || []).map((item) => [item.relationship_id, item]));
  const evalById = new Map((result.evaluations || []).map((item) => [item.evaluation_id, item]));

  const overviewText = result.evaluations?.[0]?.finding || result.relationships?.[0]?.effect;
  if (overviewText) {
    const overview = el("section", "panel result-overview");
    overview.append(el("p", "eyebrow", "DESIGN READ"), el("p", "overview-text", overviewText));
    if (result.evaluations?.[0]?.impact) overview.append(el("p", "overview-text muted", `Likely impact: ${result.evaluations[0].impact}`));
    root.append(overview);
  }

  const observations = (result.observations || []).map((item) => findingCard(item.role || "Visible element", item.text, { refs: item.evidence_refs, evidenceById }));
  addSection(root, "â—‰", "Visual observations", observations);

  const hierarchy = result.hierarchy || {};
  const hierarchyCards = [];
  for (const item of hierarchy.apparent_order || []) {
    const obs = obsById.get(item.observation_ref);
    hierarchyCards.push(findingCard(`${item.rank}. ${obs?.role || obs?.text || "Visual element"}`, item.prominence_evidence, { badge: "Apparent priority" }));
  }
  for (const flow of hierarchy.reading_flow || []) {
    const card = el("article", "finding-card");
    card.append(el("h4", "", "Plausible reading path"));
    const row = el("div", "reading-flow");
    (flow.sequence || []).forEach((id, index) => {
      if (index) row.append(el("span", "flow-arrow", "â†’"));
      const obs = obsById.get(id); row.append(el("span", "flow-step", obs?.role || obs?.text || id));
    });
    card.append(row);
    if (flow.rationale) card.append(el("p", "", flow.rationale));
    hierarchyCards.push(card);
  }
  addSection(root, "â†—", "Visual hierarchy & reading flow", hierarchyCards);

  const relationshipCards = (result.relationships || []).map((item) => {
    const subjects = [...(item.subject_refs || []), ...(item.object_refs || [])].map((id) => obsById.get(id)?.role || id);
    const label = subjects.length ? subjects.join(" â†” ") : item.relation;
    return findingCard(label, `${item.relation}: ${item.effect}`, { why: item.interpretation, badge: item.principle || "Relationship", refs: item.evidence_refs, evidenceById });
  });
  addSection(root, "âŒ", "Element relationships", relationshipCards);

  const evalCards = (result.evaluations || []).map((item) => findingCard(item.dimension, item.finding, {
    badge: item.judgment, impact: item.impact, refs: item.evidence_refs, evidenceById,
  }));
  addSection(root, "â—ˆ", "Design evaluation", evalCards);

  const recCards = (result.recommendations || []).map((item) => findingCard(item.change, item.reason, {
    badge: item.priority, impact: item.expected_impact, refs: item.evidence_refs, evidenceById,
  }));
  addSection(root, "â†—", "Actionable recommendations", recCards);

  const specialistCards = (result.specialists || []).map((item) => findingCard(item.area, item.finding, { badge: "Specialist lens", refs: item.evidence_refs, evidenceById }));
  addSection(root, "âœ³", "Relevant specialist findings", specialistCards);

  if (result.brief_context) {
    const brief = el("section", "panel result-section");
    brief.append(el("h3", "section-heading", "Brief considered"), el("p", "overview-text", result.brief_context)); root.append(brief);
  }
  const uncertainties = DemorphUncertainty.mapToCards(result.uncertainties || [], (item) => {
    const card = el("article", "finding-card uncertainty-card");
    card.append(el("h4", "", item.title));
    card.append(el("p", "", item.text));
    const guidance = el("p", "uncertainty-guidance");
    guidance.append(el("strong", "", "Next step: "), document.createTextNode(item.guidance));
    card.append(guidance);
    return card;
  });
  addSection(root, "!", "Uncertainty & limitations", uncertainties, "uncertainty-panel");
  showState("resultState");
}

async function openResult(id) {
  const record = await api(`/api/results/${id}`);
  state.analysisId = id;
  if (!["complete", "partial"].includes(record.status) || !record.result) {
    $("#errorTitle").textContent = "This analysis did not complete.";
    $("#errorMessage").textContent = record.error_message || "No completed result is available.";
    $("#retryBtn").classList.add("hidden");
    showState("errorState"); return;
  }
  renderResult(record);
  document.querySelectorAll(".history-item").forEach((item) => item.classList.toggle("active", item.dataset.id === id));
}

function renderHistory(items) {
  state.history = items;
  const list = $("#historyList"); list.replaceChildren();
  $("#historyCount").textContent = String(items.length);
  if (!items.length) { list.append(el("p", "muted small rail-empty", "Your analyses will appear here.")); return; }
  for (const item of items) {
    const button = el("button", `history-item${item.analysis_id === state.analysisId ? " active" : ""}`);
    button.type = "button"; button.dataset.id = item.analysis_id;
    const image = el("img", "history-thumb"); image.src = `/api/uploads/${item.analysis_id}`; image.alt = "";
    const copy = el("span", "history-copy");
    const historyStatus = ["complete", "partial"].includes(item.status) ? `${item.status === "partial" ? "Partial Â· " : ""}${new Date(item.created_at).toLocaleDateString()}` : item.status === "failed" ? "Analysis failed" : item.status;
    copy.append(el("strong", "", item.source_filename), el("small", "", historyStatus));
    button.append(image, copy);
    button.addEventListener("click", () => openResult(item.analysis_id).catch((error) => uploadError(error.message)));
    list.append(button);
  }
}

async function refreshHistory() {
  try { const result = await api("/api/history"); renderHistory(result.items || []); }
  catch { /* The main analysis view remains usable if history refresh is interrupted. */ }
}

function showUploadView() {
  if (state.busy) return;
  state.analysisId = null; showState("welcomeState"); resetUpload(); $("#briefInput").value = "";
  $("#navNew").classList.add("selected");
  document.querySelectorAll(".history-item").forEach((item) => item.classList.remove("active"));
}

function setupUpload() {
  const zone = $("#dropZone");
  $("#browseBtn").addEventListener("click", (event) => { event.stopPropagation(); $("#fileInput").click(); });
  $("#replaceBtn").addEventListener("click", (event) => { event.stopPropagation(); $("#fileInput").click(); });
  $("#changeFileBtn").addEventListener("click", () => $("#fileInput").click());
  $("#fileInput").addEventListener("change", (event) => chooseFile(event.target.files?.[0]));
  zone.addEventListener("click", (event) => { if (!event.target.closest("button")) $("#fileInput").click(); });
  zone.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("#fileInput").click(); } });
  for (const name of ["dragenter", "dragover"]) zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add("dragover"); });
  for (const name of ["dragleave", "drop"]) zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.remove("dragover"); });
  zone.addEventListener("drop", (event) => chooseFile(event.dataTransfer?.files?.[0]));
  $("#removeImageBtn").addEventListener("click", resetUpload);
}

setupUpload();
$("#analyzeBtn").addEventListener("click", startAnalysis);
$("#cancelBtn").addEventListener("click", cancelAnalysis);
$("#retryBtn").addEventListener("click", startAnalysis);
$("#newAnalysisBtn").addEventListener("click", showUploadView);
$("#navNew").addEventListener("click", showUploadView);
checkHealth(); refreshHistory();
