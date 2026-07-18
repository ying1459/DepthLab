const elements = {
  form: document.querySelector("#depthForm"),
  input: document.querySelector("#videoInput"),
  dropZone: document.querySelector("#dropZone"),
  dropEmpty: document.querySelector("#dropEmpty"),
  selected: document.querySelector("#videoSelected"),
  preview: document.querySelector("#sourcePreview"),
  replace: document.querySelector("#replaceButton"),
  fileName: document.querySelector("#fileName"),
  fileMeta: document.querySelector("#fileMeta"),
  fileType: document.querySelector("#fileType"),
  submit: document.querySelector("#submitButton"),
  progressPanel: document.querySelector("#progressPanel"),
  progressBar: document.querySelector("#progressBar"),
  progressPercent: document.querySelector("#progressPercent"),
  progressMessage: document.querySelector("#progressMessage"),
  progressFrames: document.querySelector("#progressFrames"),
  cancel: document.querySelector("#cancelButton"),
  resultPanel: document.querySelector("#resultPanel"),
  resultVideo: document.querySelector("#resultVideo"),
  resultStats: document.querySelector("#resultStats"),
  download: document.querySelector("#downloadButton"),
  newTask: document.querySelector("#newTaskButton"),
  smoothing: document.querySelector("#smoothing"),
  smoothValue: document.querySelector("#smoothValue"),
  systemBadge: document.querySelector("#systemBadge"),
  toast: document.querySelector("#toast"),
};

let selectedFile = null;
let sourceUrl = null;
let activeJobId = null;
let pollTimer = null;
let currentResultUrl = null;

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return "时长未知";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.remove("hidden");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.add("hidden"), 4200);
}

function setFile(file) {
  if (!file || !file.type.startsWith("video/") && !/\.(mkv|m4v)$/i.test(file.name)) {
    showToast("请选择 MP4、MOV、AVI、WebM 或 MKV 视频");
    return;
  }
  selectedFile = file;
  if (sourceUrl) URL.revokeObjectURL(sourceUrl);
  sourceUrl = URL.createObjectURL(file);
  elements.preview.src = sourceUrl;
  elements.preview.load();
  elements.fileName.textContent = file.name;
  elements.fileType.textContent = (file.name.split(".").pop() || "VIDEO").toUpperCase();
  elements.fileMeta.textContent = `${formatBytes(file.size)} · 正在读取画面信息`;
  elements.dropEmpty.classList.add("hidden");
  elements.selected.classList.remove("hidden");
  elements.replace.classList.remove("hidden");
  elements.submit.disabled = false;

  elements.preview.onloadedmetadata = () => {
    const resolution = elements.preview.videoWidth && elements.preview.videoHeight
      ? ` · ${elements.preview.videoWidth}×${elements.preview.videoHeight}` : "";
    elements.fileMeta.textContent = `${formatBytes(file.size)} · ${formatTime(elements.preview.duration)}${resolution}`;
    elements.preview.currentTime = Math.min(1, elements.preview.duration / 3 || 0);
  };
}

elements.input.addEventListener("change", (event) => setFile(event.target.files[0]));
elements.replace.addEventListener("click", () => elements.input.click());
elements.dropZone.addEventListener("click", (event) => {
  if (event.target.closest("video") || event.target.closest(".video-overlay")) return;
  elements.input.click();
});
elements.dropZone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    elements.input.click();
  }
});

["dragenter", "dragover"].forEach((name) => elements.dropZone.addEventListener(name, (event) => {
  event.preventDefault();
  elements.dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((name) => elements.dropZone.addEventListener(name, (event) => {
  event.preventDefault();
  elements.dropZone.classList.remove("dragging");
}));
elements.dropZone.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));

elements.smoothing.addEventListener("input", () => {
  elements.smoothValue.textContent = `${elements.smoothing.value}%`;
  const value = elements.smoothing.value;
  elements.smoothing.style.background = `linear-gradient(90deg, var(--acid) ${value}%, #29312e ${value}%)`;
});

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    elements.systemBadge.querySelector("span").textContent = `${data.device} · 已就绪`;
  } catch {
    elements.systemBadge.querySelector("span").textContent = "本地服务未连接";
    elements.systemBadge.querySelector("i").style.background = "var(--danger)";
  }
}

function setWorking(working) {
  elements.form.classList.toggle("hidden", working);
  elements.progressPanel.classList.toggle("hidden", !working);
  if (working) elements.resultPanel.classList.add("hidden");
}

function updateProgress(job) {
  const progress = Math.max(0, Math.min(100, job.progress || 0));
  elements.progressBar.style.width = `${progress}%`;
  elements.progressPercent.textContent = `${Math.round(progress)}%`;
  elements.progressMessage.textContent = job.message || "正在处理";
  elements.progressFrames.textContent = job.total_frames
    ? `已处理 ${job.current_frame.toLocaleString()} / ${job.total_frames.toLocaleString()} 帧`
    : job.state === "queued" ? "任务正在排队" : "正在初始化推理引擎";
}

async function pollJob() {
  if (!activeJobId) return;
  try {
    const response = await fetch(`/api/jobs/${activeJobId}`);
    if (!response.ok) throw new Error("无法读取任务状态");
    const job = await response.json();
    updateProgress(job);

    if (job.state === "completed") {
      window.clearInterval(pollTimer);
      showResult(job);
    } else if (job.state === "failed") {
      window.clearInterval(pollTimer);
      setWorking(false);
      showToast(job.error || "处理失败，请检查视频后重试");
      elements.submit.disabled = false;
    } else if (job.state === "cancelled") {
      window.clearInterval(pollTimer);
      setWorking(false);
      showToast("任务已取消");
      elements.submit.disabled = false;
    }
  } catch (error) {
    window.clearInterval(pollTimer);
    setWorking(false);
    showToast(error.message || "本地服务连接中断");
  }
}

function showResult(job) {
  elements.progressPanel.classList.add("hidden");
  elements.resultPanel.classList.remove("hidden");
  currentResultUrl = `/api/jobs/${job.id}/result`;
  elements.resultVideo.onerror = () => showToast("预览加载失败，仍可点击“保存 MP4”导出文件");
  elements.resultVideo.src = `/api/jobs/${job.id}/preview`;
  elements.resultVideo.load();
  elements.download.href = currentResultUrl;
  const meta = job.metadata || {};
  elements.resultStats.innerHTML = `
    <div><strong>${meta.width || "—"}×${meta.height || "—"}</strong><span>分辨率</span></div>
    <div><strong>${meta.fps || "—"} FPS</strong><span>帧率</span></div>
    <div><strong>${meta.frames || "—"}</strong><span>总帧数</span></div>
    <div><strong>${meta.device || "—"}</strong><span>处理设备</span></div>`;
  elements.resultPanel.scrollIntoView({ behavior: "smooth", block: "center" });
}

elements.download.addEventListener("click", async (event) => {
  if (!activeJobId || !currentResultUrl) {
    event.preventDefault();
    showToast("还没有可以保存的结果");
    return;
  }

  if (!window.pywebview?.api?.save_result) return;

  event.preventDefault();
  const label = elements.download.querySelector("span");
  const previousLabel = label.textContent;
  elements.download.setAttribute("aria-disabled", "true");
  label.textContent = "正在保存…";
  try {
    const result = await window.pywebview.api.save_result(activeJobId);
    if (result?.ok) {
      showToast(`已保存到：${result.path}`);
    } else if (!result?.cancelled) {
      showToast(result?.error || "保存失败，请重试");
    }
  } catch (error) {
    showToast(error?.message || "无法打开保存窗口");
  } finally {
    elements.download.removeAttribute("aria-disabled");
    label.textContent = previousLabel;
  }
});

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) return;

  const data = new FormData();
  data.append("video", selectedFile, selectedFile.name);
  data.append("model", "small");
  data.append("mode", document.querySelector("#mode").value);
  data.append("palette", document.querySelector("#palette").value);
  data.append("max_side", document.querySelector("#maxSide").value);
  data.append("output_fps", document.querySelector("#outputFps").value);
  data.append("smoothing", (Number(elements.smoothing.value) / 100).toString());
  data.append("invert", document.querySelector("#invert").checked.toString());
  data.append("keep_audio", document.querySelector("#keepAudio").checked.toString());

  elements.submit.disabled = true;
  setWorking(true);
  updateProgress({ progress: 0, message: "正在上传到本地处理队列", state: "queued" });
  try {
    const response = await fetch("/api/jobs", { method: "POST", body: data });
    const job = await response.json();
    if (!response.ok) throw new Error(job.detail || "无法创建任务");
    activeJobId = job.id;
    updateProgress(job);
    pollTimer = window.setInterval(pollJob, 800);
    pollJob();
  } catch (error) {
    setWorking(false);
    elements.submit.disabled = false;
    showToast(error.message || "任务创建失败");
  }
});

elements.cancel.addEventListener("click", async () => {
  if (!activeJobId) return;
  elements.cancel.disabled = true;
  try {
    await fetch(`/api/jobs/${activeJobId}/cancel`, { method: "POST" });
    elements.progressMessage.textContent = "正在安全停止任务";
  } finally {
    elements.cancel.disabled = false;
  }
});

elements.newTask.addEventListener("click", () => {
  activeJobId = null;
  currentResultUrl = null;
  elements.resultVideo.removeAttribute("src");
  elements.resultVideo.load();
  elements.resultPanel.classList.add("hidden");
  elements.form.classList.remove("hidden");
  elements.submit.disabled = !selectedFile;
  window.scrollTo({ top: 0, behavior: "smooth" });
});

loadHealth();
