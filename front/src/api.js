/* ==========================================================
   API layer. Real accounts talk to the FastAPI backend.
   The built-in demo account runs entirely in the browser, so the
   UI can be explored without MongoDB / Ollama running.
   ========================================================== */
import { translate, currentLang } from "./i18n.jsx";

export const API = "http://127.0.0.1:8000";

export const DEMO = {
  email: "demo@carecompanion.ai",
  password: "Demo@1234",
  token: "demo-token",
};

export const getToken = () => localStorage.getItem("token");
export const isDemo = () => getToken() === DEMO.token;

const reply = (data, ok = true, status = 200) => ({ ok, status, json: async () => data });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---------------- auth ---------------- */
export async function login(email, password) {
  if (email.trim().toLowerCase() === DEMO.email && password === DEMO.password) {
    return { ok: true, token: DEMO.token };
  }
  const res = await fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (res.ok && data.access_token) return { ok: true, token: data.access_token };
  return { ok: false, error: data.detail || "Incorrect email or password." };
}

export async function register(email, password) {
  const res = await fetch("/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (res.ok) return { ok: true };
  const err = await res.json().catch(() => ({}));
  return { ok: false, error: err.detail || "Registration failed." };
}

/* ---------------- authenticated requests ---------------- */
export async function request(path, options = {}) {
  if (isDemo()) return mock(path, options);
  return fetch(`${API}${path}`, {
    ...options,
    headers: { ...(options.headers || {}), Authorization: `Bearer ${getToken()}` },
  });
}

/* ---------------- demo backend ---------------- */
const LS_SUMMARIES = "demo_summaries";
let convo = []; // [{role: "patient" | "doctor", message}]
let lastSession = null;

const EMERGENCY = ["chest pain", "can't breathe", "cannot breathe", "shortness of breath", "difficulty breathing", "unconscious", "stroke", "severe bleeding", "suicid", "seizure", "face drooping"];
const URGENT = ["fever", "vomit", "blood", "severe", "dizz", "fainting", "infection", "swollen", "persistent", "worse"];

const SYMPTOMS = ["headache", "fever", "cough", "sore throat", "fatigue", "tired", "nausea", "vomiting", "dizziness", "dizzy", "back pain", "chest pain", "shortness of breath", "rash", "diarrhea", "runny nose", "body ache", "chills", "stomach pain"];

const CONDITIONS = [
  { keys: ["fever", "cough", "sore throat", "body ache", "chills", "runny nose"], name: "Viral upper respiratory infection (common cold / flu)", note: "Rest, fluids and over-the-counter symptom relief usually help." },
  { keys: ["headache", "nausea", "dizz"], name: "Migraine or tension-type headache", note: "Often triggered by stress, dehydration or poor sleep." },
  { keys: ["stomach", "nausea", "vomit", "diarrhea"], name: "Gastroenteritis", note: "Stay hydrated; seek care if symptoms last more than 2 days." },
  { keys: ["back pain"], name: "Mechanical (musculoskeletal) back strain", note: "Gentle movement is usually better than bed rest." },
  { keys: ["tired", "fatigue", "dizz"], name: "Fatigue related to sleep, anaemia or low blood pressure", note: "Blood tests can help rule out common causes." },
  { keys: ["chest pain", "shortness of breath"], name: "Cardiac or pulmonary cause — needs urgent evaluation", note: "Do not wait; seek emergency care." },
];


/* Map common non-English symptom words to the English keywords above, so the demo works in every UI language. */
const NORMALIZE = {
  "dolor de pecho": "chest pain", "fiebre": "fever", "dolor de cabeza": "headache", "tos": "cough", "dolor de garganta": "sore throat", "mareo": "dizzy", "cansad": "tired", "dolor de espalda": "back pain", "espalda": "back pain", "náuseas": "nausea", "falta de aire": "shortness of breath",
  "douleur thoracique": "chest pain", "fièvre": "fever", "mal de tête": "headache", "toux": "cough", "mal à la gorge": "sore throat", "étourdi": "dizzy", "fatigu": "tired", "mal au dos": "back pain", "bas du dos": "back pain", "nausée": "nausea", "essoufflement": "shortness of breath",
  "सीने में दर्द": "chest pain", "बुखार": "fever", "सिरदर्द": "headache", "खांसी": "cough", "गला": "sore throat", "चक्कर": "dizzy", "थकान": "tired", "पीठ": "back pain", "मतली": "nausea", "सांस": "shortness of breath",
  "ఛాతీ నొప్పి": "chest pain", "జ్వరం": "fever", "తలనొప్పి": "headache", "దగ్గు": "cough", "గొంతు": "sore throat", "తల తిరు": "dizzy", "అలసట": "tired", "నడుము": "back pain", "వికారం": "nausea", "ఊపిరి": "shortness of breath",
  "ألم في الصدر": "chest pain", "حمى": "fever", "صداع": "headache", "سعال": "cough", "الحلق": "sore throat", "دوار": "dizzy", "تعب": "tired", "الظهر": "back pain", "غثيان": "nausea", "ضيق في التنفس": "shortness of breath",
};
const normalize = (text) => Object.entries(NORMALIZE).reduce((acc, [k, v]) => acc.split(k).join(` ${v} `), text.toLowerCase());
const has = (text, list) => list.some((k) => text.includes(k));
const allText = () => normalize(convo.filter((m) => m.role === "patient").map((m) => m.message).join(" "));

function triage(text, L) {
  if (has(text, EMERGENCY)) return { level: "Emergency", reason: translate(L, "demo.rEm") };
  if (has(text, URGENT)) return { level: "Urgent", reason: translate(L, "demo.rUr") };
  return { level: "Routine", reason: translate(L, "demo.rRo") };
}

function structured(text) {
  const onset = text.match(/(\d+|a|an|one|two|three)\s*(hour|day|week|month)s?/);
  const severity = /severe|worst|unbearable/.test(text) ? "severe" : /moderate|quite|bad/.test(text) ? "moderate" : "mild";
  const found = [...new Set(SYMPTOMS.filter((s) => text.includes(s)))];
  return {
    chief_complaint: convo.find((m) => m.role === "patient")?.message.slice(0, 120) || "",
    onset: onset ? onset[0] : "",
    severity,
    associated_symptoms: found,
    risk_factors: [],
    vitals: {},
  };
}

function doctorText(turn, level, L) {
  if (level === "Emergency") return translate(L, "demo.em");
  if (turn <= 3) return translate(L, `demo.q${turn}`);
  return translate(L, level === "Urgent" ? "demo.urgent" : "demo.routine");
}

async function mock(rawPath, options) {
  await wait(500 + Math.random() * 500);
  const [path, qs] = rawPath.split("?");
  const L = new URLSearchParams(qs || "").get("language") || currentLang();
  const body = options.body && typeof options.body === "string" ? JSON.parse(options.body) : {};
  const saved = () => JSON.parse(localStorage.getItem(LS_SUMMARIES) || "[]");

  if (path === "/api/me") return reply({ email: DEMO.email });

  if (path === "/api/chat") {
    const lc = body.language || L;
    if (body.session_id !== lastSession) { convo = []; lastSession = body.session_id; }
    convo.push({ role: "patient", message: body.message });
    const text = allText();
    const t = triage(text, lc);
    const turn = convo.filter((m) => m.role === "patient").length;
    const answer = doctorText(turn, t.level, lc);
    convo.push({ role: "doctor", message: answer });
    return reply({ reply: answer, triage: t, structured: structured(text) });
  }

  if (path === "/api/generate_summary") {
    if (convo.length < 2) return reply({ summary: "No conversation found yet." });
    const text = allText();
    const s = structured(text);
    const t = triage(text, L);
    const tr = (k) => translate(L, k);
    const summary =
      `**${tr("demo.complaint")}:** ${s.chief_complaint}\n` +
      `**${tr("demo.onset")}:** ${s.onset || tr("demo.notSpec")}\n` +
      `**${tr("demo.sevl")}:** ${translate(L, `sev.${s.severity}`)}\n` +
      `**${tr("demo.assoc")}:** ${s.associated_symptoms.join(", ") || tr("demo.noneRep")}\n` +
      `**${tr("demo.tri")}:** ${translate(L, `level.${t.level}`)} — ${t.reason}`;
    const list = saved();
    const id = "demo-" + Date.now();
    list.unshift({ _id: id, summary_text: summary, timestamp: new Date().toISOString(), conversation: [...convo] });
    localStorage.setItem(LS_SUMMARIES, JSON.stringify(list));
    return reply({ summary, saved: true, id });
  }

  if (path === "/api/generate_diagnosis") {
    if (convo.length < 2) return reply({ diagnosis: "Please have a conversation first." });
    const text = allText();
    const ranked = CONDITIONS.map((c) => ({ ...c, score: c.keys.filter((k) => text.includes(k)).length }))
      .filter((c) => c.score > 0).sort((a, b) => b.score - a.score).slice(0, 4);
    if (!ranked.length) return reply({ diagnosis: "There isn't enough information yet to suggest likely conditions. Please describe your symptoms in more detail." });
    const lines = ranked.map((c, i) => `${i + 1}. **${c.name}** — ${translate(L, `demo.rank${Math.min(i, 2)}`)}. ${c.note}`);
    return reply({ diagnosis: lines.join("\n") + "\n\n" + translate(L, "demo.dxNote") });
  }

  if (path === "/api/summaries") return reply({ history: saved().map(({ _id, summary_text, timestamp }) => ({ _id, summary_text, timestamp })) });

  if (path.startsWith("/api/summaries/")) {
    const doc = saved().find((d) => d._id === path.split("/").pop());
    return doc ? reply(doc) : reply({ detail: "Summary not found" }, false, 404);
  }

  return reply({ detail: "Not found" }, false, 404);
}
