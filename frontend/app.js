/* ------------------------------------------------------------------
 * app.js — Communication Assessment Platform (frontend)
 *
 * Responsibilities:
 *   1. Screen/state management (landing -> assessment -> result -> recruiter)
 *   2. Talking to the Flask backend (/assessment/* endpoints)
 *   3. Capturing candidate answers by voice (Web Speech API) or text
 *   4. Real-time tonality signal analysis from the microphone using the
 *      Web Audio API (AudioAnalyzer class below) — this runs entirely
 *      client-side and only a compact numeric feature summary is sent
 *      to the server (see backend/scoring.py::score_tonality).
 * ------------------------------------------------------------------ */

const API_BASE = ""; // same-origin (Flask also serves this static frontend)

const STAGE_LABELS = {
  greeting: "Introduction",
  scenario: "Vendor scenario",
  followup1: "Follow-up 1",
  followup2: "Follow-up 2",
  closing: "Closing",
  done: "Done",
};
const STAGE_SEQUENCE = ["greeting", "scenario", "followup1", "followup2", "closing"];

// ---------------------------------------------------------------------
// Tiny app state
// ---------------------------------------------------------------------
const state = {
  sessionId: null,
  candidateName: "",
  accentLang: "en-IN",
  currentStage: null,
  micSupported: false,
};

// ---------------------------------------------------------------------
// Screen management
// ---------------------------------------------------------------------
function showScreen(id) {
  document.querySelectorAll(".screen").forEach((el) => {
    el.dataset.active = el.id === id ? "true" : "false";
  });
}

// ---------------------------------------------------------------------
// AudioAnalyzer — real-time volume + pitch tracking via Web Audio API
// ---------------------------------------------------------------------
class AudioAnalyzer {
  constructor(stream) {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    this.ctx = new AudioCtx();
    this.source = this.ctx.createMediaStreamSource(stream);
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    this.source.connect(this.analyser);

    this.buffer = new Float32Array(this.analyser.fftSize);
    this.volumeSamples = [];
    this.pitchSamples = [];
    this.startTime = performance.now();
    this._raf = null;
    this.latestVolume = 0; // 0..1, for the live meter UI
  }

  start(onFrame) {
    const tick = () => {
      this.analyser.getFloatTimeDomainData(this.buffer);

      const rms = computeRMS(this.buffer);
      this.volumeSamples.push(rms);
      this.latestVolume = rms;

      // Only attempt pitch detection on frames with enough energy
      // (silence/background noise produces meaningless pitch estimates)
      if (rms > 0.02) {
        const freq = autoCorrelatePitch(this.buffer, this.ctx.sampleRate);
        if (freq && freq > 60 && freq < 500) {
          // human voice fundamental frequency range
          this.pitchSamples.push(freq);
        }
      }

      if (onFrame) onFrame(rms);
      this._raf = requestAnimationFrame(tick);
    };
    this._raf = requestAnimationFrame(tick);
  }

  stop() {
    if (this._raf) cancelAnimationFrame(this._raf);
    const durationSec = (performance.now() - this.startTime) / 1000;
    try {
      this.source.disconnect();
      this.ctx.close();
    } catch (e) {
      /* already closed - ignore */
    }
    return this._summarize(durationSec);
  }

  _summarize(durationSec) {
    const vol = this.volumeSamples;
    const avgVolume = vol.length ? mean(vol) : 0;
    const volStd = vol.length ? stddev(vol, avgVolume) : 0;
    const silenceFrames = vol.filter((v) => v < 0.015).length;
    const silenceRatio = vol.length ? silenceFrames / vol.length : 0;

    const pitchVar = this.pitchSamples.length > 4 ? stddev(this.pitchSamples, mean(this.pitchSamples)) : 0;

    return {
      duration_sec: Math.round(durationSec * 10) / 10,
      avg_volume_rms: round3(avgVolume),
      volume_std: round3(volStd),
      pitch_variance_hz: Math.round(pitchVar * 10) / 10,
      silence_ratio: round3(silenceRatio),
      // words_per_minute is filled in by caller once the transcript is known
    };
  }
}

function computeRMS(buf) {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
  return Math.sqrt(sum / buf.length);
}

function mean(arr) {
  return arr.reduce((a, b) => a + b, 0) / arr.length;
}

function stddev(arr, m) {
  const variance = arr.reduce((a, b) => a + (b - m) * (b - m), 0) / arr.length;
  return Math.sqrt(variance);
}

function round3(n) {
  return Math.round(n * 1000) / 1000;
}

/**
 * Classic autocorrelation-based pitch detector (time-domain).
 * Returns estimated fundamental frequency in Hz, or -1 if no clear
 * periodicity was found (unvoiced / noisy frame).
 */
function autoCorrelatePitch(buf, sampleRate) {
  const SIZE = buf.length;
  let rms = 0;
  for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i];
  rms = Math.sqrt(rms / SIZE);
  if (rms < 0.01) return -1;

  // trim silence at start/end for a tighter autocorrelation window
  let r1 = 0, r2 = SIZE - 1;
  const thresh = 0.2;
  for (let i = 0; i < SIZE / 2; i++) {
    if (Math.abs(buf[i]) > thresh) { r1 = i; break; }
  }
  for (let i = 1; i < SIZE / 2; i++) {
    if (Math.abs(buf[SIZE - i]) > thresh) { r2 = SIZE - i; break; }
  }
  const trimmed = buf.slice(r1, r2);
  const n = trimmed.length;
  if (n < 8) return -1;

  const c = new Array(n).fill(0);
  for (let lag = 0; lag < n; lag++) {
    let sum = 0;
    for (let i = 0; i < n - lag; i++) sum += trimmed[i] * trimmed[i + lag];
    c[lag] = sum;
  }

  let d = 0;
  while (d < n - 1 && c[d] > c[d + 1]) d++;

  let maxVal = -1, maxPos = -1;
  for (let i = d; i < n; i++) {
    if (c[i] > maxVal) { maxVal = c[i]; maxPos = i; }
  }
  if (maxPos <= 0) return -1;

  let t0 = maxPos;
  // parabolic interpolation for sub-sample precision
  const x1 = c[t0 - 1] || 0, x2 = c[t0], x3 = c[t0 + 1] || 0;
  const a = (x1 + x3 - 2 * x2) / 2;
  const b = (x3 - x1) / 2;
  if (a) t0 = t0 - b / (2 * a);

  return sampleRate / t0;
}

// ---------------------------------------------------------------------
// Speech recognition wrapper (Web Speech API, with graceful fallback)
// ---------------------------------------------------------------------
function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

// ---------------------------------------------------------------------
// Recorder controller — ties mic capture + speech-to-text + tonality
// analysis together for a single candidate answer.
// ---------------------------------------------------------------------
class AnswerRecorder {
  constructor(lang) {
    this.lang = lang;
    this.recognition = null;
    this.analyzer = null;
    this.stream = null;
    this.finalTranscript = "";
    this.interimTranscript = "";
    this.recording = false;
  }

  async start({ onInterim, onLevel }) {
    this.finalTranscript = "";
    this.interimTranscript = "";

    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.analyzer = new AudioAnalyzer(this.stream);
    this.analyzer.start((rms) => onLevel && onLevel(rms));

    const SR = getSpeechRecognition();
    if (SR) {
      this.recognition = new SR();
      this.recognition.lang = this.lang;
      this.recognition.continuous = true;
      this.recognition.interimResults = true;

      this.recognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i];
          if (res.isFinal) {
            this.finalTranscript += res[0].transcript + " ";
          } else {
            interim += res[0].transcript;
          }
        }
        this.interimTranscript = interim;
        onInterim && onInterim((this.finalTranscript + " " + interim).trim());
      };

      this.recognition.onerror = (e) => {
        console.warn("SpeechRecognition error:", e.error);
      };

      // auto-restart if the browser stops it early (common on some
      // implementations after ~60s of silence) while still "recording"
      this.recognition.onend = () => {
        if (this.recording) {
          try { this.recognition.start(); } catch (e) { /* ignore */ }
        }
      };

      this.recognition.start();
    }

    this.recording = true;
  }

  stop() {
    this.recording = false;
    if (this.recognition) {
      try { this.recognition.stop(); } catch (e) { /* ignore */ }
    }
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
    }
    const audioFeatures = this.analyzer ? this.analyzer.stop() : null;
    const transcript = (this.finalTranscript + " " + this.interimTranscript).trim();

    if (audioFeatures && transcript) {
      const wordCount = transcript.split(/\s+/).filter(Boolean).length;
      const minutes = Math.max(audioFeatures.duration_sec / 60, 1 / 60);
      audioFeatures.words_per_minute = Math.round((wordCount / minutes) * 10) / 10;
    }

    return { transcript, audioFeatures };
  }
}

// ---------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------
async function apiPost(path, body) {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function apiGet(path) {
  const res = await fetch(API_BASE + path);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------
// Chat rendering
// ---------------------------------------------------------------------
const chatLog = () => document.getElementById("chat-log");

function addBotBubble(text) {
  const el = document.createElement("div");
  el.className = "bubble bubble--bot";
  el.innerHTML = `<span class="bubble__tag">Interviewer</span>${escapeHtml(text)}`;
  chatLog().appendChild(el);
  scrollChatToBottom();
}

function addCandidateBubble(text, mode) {
  const el = document.createElement("div");
  el.className = "bubble bubble--candidate";
  const tag = mode === "voice" ? "You (voice)" : "You (typed)";
  el.innerHTML = `<span class="bubble__tag">${tag}</span>${escapeHtml(text)}`;
  chatLog().appendChild(el);
  scrollChatToBottom();
}

function addScoreNote(analysis) {
  const el = document.createElement("div");
  el.className = "bubble bubble--score";
  const parts = [];
  if (analysis.pitch.score !== null) parts.push(`Pitch ${analysis.pitch.score}/10`);
  if (analysis.vocabulary.score !== null) parts.push(`Vocabulary ${analysis.vocabulary.score}/10`);
  if (analysis.tonality.score !== null) parts.push(`Tonality ${analysis.tonality.score}/10`);
  el.textContent = parts.length ? `Noted — ${parts.join(" · ")}` : "Noted.";
  chatLog().appendChild(el);
  scrollChatToBottom();
}

function scrollChatToBottom() {
  const c = chatLog();
  c.scrollTop = c.scrollHeight;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---------------------------------------------------------------------
// Stage progress bar
// ---------------------------------------------------------------------
function renderStageProgress(currentStage) {
  const wrap = document.getElementById("stage-progress");
  wrap.innerHTML = "";
  const currentIdx = STAGE_SEQUENCE.indexOf(currentStage);
  STAGE_SEQUENCE.forEach((stage, i) => {
    const seg = document.createElement("div");
    seg.className = "seg";
    if (currentIdx === -1 || i < currentIdx) seg.dataset.state = "done";
    else if (i === currentIdx) seg.dataset.state = "active";
    wrap.appendChild(seg);
  });
}

// ---------------------------------------------------------------------
// Elapsed timer
// ---------------------------------------------------------------------
let elapsedTimerHandle = null;
function startElapsedTimer() {
  const startedAt = Date.now();
  const el = document.getElementById("elapsed-timer");
  clearInterval(elapsedTimerHandle);
  elapsedTimerHandle = setInterval(() => {
    const s = Math.floor((Date.now() - startedAt) / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, "0");
    const ss = String(s % 60).padStart(2, "0");
    el.textContent = `${mm}:${ss}`;
  }, 1000);
}

// ---------------------------------------------------------------------
// Main flow wiring
// ---------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  const SR = getSpeechRecognition();
  state.micSupported = !!SR && !!navigator.mediaDevices;
  const note = document.getElementById("mic-support-note");
  if (!state.micSupported) {
    note.textContent =
      "Voice input isn't supported in this browser — you can still complete the assessment by typing. Try Chrome or Edge for voice input.";
  } else {
    note.textContent = "Voice answers work best in a quiet room with Chrome or Edge.";
  }

  document.getElementById("start-form").addEventListener("submit", onStartAssessment);
  document.getElementById("send-btn").addEventListener("click", onSendText);
  document.getElementById("mic-btn").addEventListener("click", onToggleMic);
  document.getElementById("text-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSendText();
    }
  });
  document.getElementById("restart-btn").addEventListener("click", () => window.location.reload());
  document.getElementById("toggle-transcript-btn").addEventListener("click", toggleTranscript);
  document.getElementById("recruiter-view-btn").addEventListener("click", openRecruiterView);
  document.getElementById("recruiter-back-btn").addEventListener("click", () => showScreen("screen-result"));
});

let recorder = null;

async function onStartAssessment(e) {
  e.preventDefault();
  const nameInput = document.getElementById("candidate-name");
  const accentSelect = document.getElementById("accent-select");
  state.candidateName = nameInput.value.trim();
  state.accentLang = accentSelect.value;

  const btn = document.getElementById("start-btn");
  btn.disabled = true;
  btn.textContent = "Starting…";

  try {
    const data = await apiPost("/assessment/start", {
      candidate_name: state.candidateName || null,
    });
    state.sessionId = data.session_id;
    state.currentStage = data.stage;

    showScreen("screen-assessment");
    renderStageProgress(state.currentStage);
    startElapsedTimer();
    addBotBubble(data.bot_message);
  } catch (err) {
    alert("Couldn't start the assessment: " + err.message);
    btn.disabled = false;
    btn.textContent = "Start assessment";
  }
}

async function onSendText() {
  const input = document.getElementById("text-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  await submitAnswer(text, "text", null);
}

async function onToggleMic() {
  if (!state.micSupported) {
    alert("Voice input isn't supported in this browser. Please type your answer instead.");
    return;
  }
  const btn = document.getElementById("mic-btn");
  const label = document.getElementById("mic-btn-label");
  const meterWrap = document.getElementById("meter-wrap");
  const meterFill = document.getElementById("meter-fill");
  const recordTime = document.getElementById("record-time");
  const hint = document.getElementById("live-transcript-hint");

  if (!recorder || !recorder.recording) {
    try {
      recorder = new AnswerRecorder(state.accentLang);
      const recStart = performance.now();
      await recorder.start({
        onInterim: (text) => {
          hint.textContent = text ? `“${text}”` : "Listening…";
        },
        onLevel: (rms) => {
          meterFill.style.width = `${Math.min(100, rms * 400)}%`;
          recordTime.textContent = `${((performance.now() - recStart) / 1000).toFixed(1)}s`;
        },
      });
      btn.setAttribute("aria-pressed", "true");
      label.textContent = "Stop & send";
      meterWrap.hidden = false;
      hint.textContent = "Listening…";
    } catch (err) {
      alert("Microphone access is needed for voice answers: " + err.message);
    }
  } else {
    const { transcript, audioFeatures } = recorder.stop();
    btn.setAttribute("aria-pressed", "false");
    label.textContent = "Speak answer";
    meterWrap.hidden = true;
    hint.textContent = "";

    if (!transcript) {
      alert("No speech was detected. Please try again or type your answer.");
      return;
    }
    await submitAnswer(transcript, "voice", audioFeatures);
  }
}

async function submitAnswer(transcript, mode, audioFeatures) {
  addCandidateBubble(transcript, mode);
  const sendBtn = document.getElementById("send-btn");
  sendBtn.disabled = true;

  try {
    const data = await apiPost(`/assessment/${state.sessionId}/response`, {
      transcript,
      input_mode: mode,
      audio_features: audioFeatures,
    });

    addScoreNote(data.analysis);
    state.currentStage = data.next_stage;
    renderStageProgress(state.currentStage);

    if (data.is_final) {
      addBotBubble(data.bot_message);
      clearInterval(elapsedTimerHandle);
      setTimeout(() => loadAndShowResult(), 900);
    } else {
      addBotBubble(data.bot_message);
    }
  } catch (err) {
    alert("Couldn't submit your answer: " + err.message);
  } finally {
    sendBtn.disabled = false;
  }
}

// ---------------------------------------------------------------------
// Result screen
// ---------------------------------------------------------------------
async function loadAndShowResult() {
  try {
    const data = await apiGet(`/assessment/${state.sessionId}/result`);
    renderResult(data);
    showScreen("screen-result");
  } catch (err) {
    alert("Couldn't load the result: " + err.message);
  }
}

function renderResult(data) {
  document.getElementById("result-candidate").textContent = data.candidate_name
    ? `Candidate: ${data.candidate_name}`
    : "Anonymous candidate";

  const pct = data.overall_percentage ?? 0;
  document.getElementById("overall-ring").style.setProperty("--pct", pct);
  document.getElementById("overall-pct").textContent = `${Math.round(pct)}%`;
  document.getElementById("overall-score-30").textContent =
    `${data.overall_score_30} / 30`;

  const bars = document.getElementById("scorebars");
  bars.innerHTML = "";
  const categories = [
    ["Pitch / self-presentation", data.pitch_score],
    ["Vocabulary", data.vocabulary_score],
    ["Tonality", data.tonality_score],
  ];
  categories.forEach(([name, score]) => {
    const tier = score == null ? "" : score >= 7 ? "good" : score <= 4.5 ? "warn" : "";
    const displayScore = score == null ? "N/A" : `${score}/10`;
    const pctWidth = score == null ? 0 : (score / 10) * 100;
    const row = document.createElement("div");
    row.className = "scorebar";
    row.innerHTML = `
      <div class="scorebar__head">
        <span class="scorebar__name">${name}</span>
        <span class="scorebar__value">${displayScore}</span>
      </div>
      <div class="scorebar__track">
        <div class="scorebar__fill" data-tier="${tier}" style="width:${pctWidth}%"></div>
      </div>`;
    bars.appendChild(row);
  });

  const strengthsEl = document.getElementById("strengths-list");
  strengthsEl.innerHTML = data.strengths.map((s) => `<li>${escapeHtml(s)}</li>`).join("");
  const improvementsEl = document.getElementById("improvements-list");
  improvementsEl.innerHTML = data.improvements.map((s) => `<li>${escapeHtml(s)}</li>`).join("");

  const transcriptEl = document.getElementById("transcript-log");
  transcriptEl.innerHTML = data.transcript
    .map(
      (t) => `
      <div class="transcript__item">
        <div class="transcript__q">${escapeHtml(t.question)}</div>
        <div class="transcript__a">${escapeHtml(t.transcript || "(no response)")}</div>
      </div>`
    )
    .join("");
  transcriptEl.hidden = true;
  document.getElementById("toggle-transcript-btn").textContent = "Show full transcript";
}

function toggleTranscript() {
  const el = document.getElementById("transcript-log");
  const btn = document.getElementById("toggle-transcript-btn");
  el.hidden = !el.hidden;
  btn.textContent = el.hidden ? "Show full transcript" : "Hide full transcript";
}

// ---------------------------------------------------------------------
// Recruiter dashboard
// ---------------------------------------------------------------------
async function openRecruiterView() {
  try {
    const data = await apiGet("/assessment/list");
    const tbody = document.getElementById("recruiter-tbody");
    tbody.innerHTML = data.sessions
      .map((s) => {
        const started = s.started_at ? new Date(s.started_at).toLocaleString() : "";
        return `
        <tr>
          <td>${escapeHtml(s.candidate_name || "Anonymous")}</td>
          <td><span class="status-pill status-pill--${s.status}">${s.status.replace("_", " ")}</span></td>
          <td>${started}</td>
          <td>${s.status === "completed" ? `<a href="#" data-sid="${s.id}" class="view-result-link">View</a>` : ""}</td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".view-result-link").forEach((a) => {
      a.addEventListener("click", async (e) => {
        e.preventDefault();
        const sid = e.target.getAttribute("data-sid");
        const result = await apiGet(`/assessment/${sid}/result`);
        renderResult(result);
        showScreen("screen-result");
      });
    });

    showScreen("screen-recruiter");
  } catch (err) {
    alert("Couldn't load recruiter dashboard: " + err.message);
  }
}
