import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Home, FileText, Stethoscope, LogOut, X, Sun, Moon, Send, Plus, History, Mic, MicOff,
  AlertTriangle, ShieldCheck, Siren, Menu, Loader2, Copy, Check, Download, PanelRight, Phone, Activity,
} from "lucide-react";
import Brand from "../components/Brand";
import RichText from "../components/RichText";
import useTheme from "../components/useTheme";
import LanguageSwitcher from "../components/LanguageSwitcher";
import NearbyDoctors from "../components/NearbyDoctors";
import { parseConditions } from "../doctors";
import { useI18n } from "../i18n";
import { request, isDemo } from "../api";
import doctorImg from "../assets/doctor.jpg";
import "../styles/chat.css";

const SUGGESTIONS = ["chat.s1", "chat.s2", "chat.s3", "chat.s4"];

const TRIAGE = {
  emergency: { cls: "emergency", Icon: Siren, step: 3 },
  urgent: { cls: "urgent", Icon: AlertTriangle, step: 2 },
  routine: { cls: "routine", Icon: ShieldCheck, step: 1 },
  normal: { cls: "routine", Icon: ShieldCheck, step: 1 },
};
const triageOf = (level) => TRIAGE[String(level || "").toLowerCase()] || TRIAGE.routine;

const newSessionId = () => "sess-" + Math.random().toString(36).slice(2, 11);
const time = (ts, lang) => new Date(ts).toLocaleTimeString(lang, { hour: "numeric", minute: "2-digit" });
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

function CopyButton({ text }) {
  const { t } = useI18n();
  const [done, setDone] = useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(String(text).replace(/\*\*/g, ""));
    setDone(true);
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <button className="copy" onClick={copy} aria-label={t("chat.copy")} title={t("chat.copy")}>
      {done ? <Check size={14} /> : <Copy size={14} />}
    </button>
  );
}

function Message({ m }) {
  const { t, lang } = useI18n();
  if (m.role === "user") {
    return (
      <div className="msg-row user">
        <div className="bubble-col user">
          <div className="bubble user"><RichText text={m.text} /></div>
          <small className="stamp">{time(m.ts, lang)}</small>
        </div>
      </div>
    );
  }

  if (m.kind === "triage") {
    const tri = triageOf(m.level);
    return (
      <div className="msg-row bot">
        <div className="avatar-spacer" />
        <div className={`triage ${tri.cls}`}>
          <tri.Icon size={20} />
          <div>
            <strong>{t("chat.triage")}: {t(`level.${m.level}`)}</strong>
            <span>{m.reason}</span>
          </div>
        </div>
      </div>
    );
  }

  if (m.kind === "doctors") return <NearbyDoctors conditions={m.conditions} />;

  if (m.kind === "summary" || m.kind === "diagnosis") {
    const isSummary = m.kind === "summary";
    const Icon = isSummary ? FileText : Stethoscope;
    return (
      <div className="msg-row bot">
        <div className="avatar-spacer" />
        <div className="report">
          <header><Icon size={17} /> {isSummary ? t("chat.caseSummary") : t("chat.possible")} <CopyButton text={m.text} /></header>
          <div className="report-body"><RichText text={m.text} /></div>
        </div>
      </div>
    );
  }

  return (
    <div className="msg-row bot">
      <img src={doctorImg} alt="" className="avatar" />
      <div className="bubble-col">
        <div className={`bubble bot ${m.kind === "error" ? "error" : ""}`}>
          <RichText text={m.text} />
        </div>
        <small className="stamp">
          {t("sv.doctor")} · {time(m.ts, lang)} {m.kind !== "error" && <CopyButton text={m.text} />}
        </small>
      </div>
    </div>
  );
}

function Insights({ triage, structured, messages }) {
  const { t: tr } = useI18n();
  const t = triage ? triageOf(triage.level) : null;
  const symptoms = structured?.associated_symptoms || [];
  const turns = messages.filter((m) => m.role === "user").length;

  return (
    <aside className="insights">
      <h3><Activity size={16} /> {tr("chat.insights")}</h3>

      <div className="ins-card">
        <span className="ins-label">{tr("ins.urgency")}</span>
        {t ? (
          <>
            <div className={`ins-level ${t.cls}`}><t.Icon size={18} /> {tr(`level.${triage.level}`)}</div>
            <div className="meter" aria-hidden>
              {[1, 2, 3].map((n) => <i key={n} className={n <= t.step ? `on ${t.cls}` : ""} />)}
            </div>
            <p className="ins-text">{triage.reason}</p>
          </>
        ) : (
          <p className="ins-text muted">{tr("ins.waiting")}</p>
        )}
      </div>

      <div className="ins-card">
        <span className="ins-label">{tr("ins.details")}</span>
        <dl className="ins-dl">
          <dt>{tr("ins.complaint")}</dt><dd>{structured?.chief_complaint || "—"}</dd>
          <dt>{tr("ins.started")}</dt><dd>{structured?.onset || "—"}</dd>
          <dt>{tr("ins.severity")}</dt><dd>{structured?.severity ? <span className={`sev ${structured.severity}`}>{tr(`sev.${structured.severity}`)}</span> : "—"}</dd>
        </dl>
      </div>

      <div className="ins-card">
        <span className="ins-label">{tr("ins.symptoms")}</span>
        {symptoms.length ? (
          <div className="tags">{symptoms.map((s) => <span key={s} className="tag">{s}</span>)}</div>
        ) : (
          <p className="ins-text muted">{tr("ins.noneYet")}</p>
        )}
      </div>

      <div className="ins-foot">{tr("ins.msgs", { n: turns })}{isDemo() && ` · ${tr("ins.demo")}`}</div>
    </aside>
  );
}

export default function Chat() {
  const navigate = useNavigate();
  const { t, lang, meta } = useI18n();
  const [theme, toggleTheme] = useTheme();
  const [messages, setMessages] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("chat_messages")) || []; } catch { return []; }
  });
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [busyAction, setBusyAction] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [showSidebar, setShowSidebar] = useState(false);
  const [showInsights, setShowInsights] = useState(true);
  const [userData, setUserData] = useState({});
  const [toast, setToast] = useState("");
  const [listening, setListening] = useState(false);
  const [triage, setTriage] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("chat_triage")); } catch { return null; }
  });
  const [structured, setStructured] = useState(() => {
    try { return JSON.parse(sessionStorage.getItem("chat_structured")); } catch { return null; }
  });
  const sessionId = useRef(sessionStorage.getItem("chat_session") || newSessionId());
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const recogRef = useRef(null);
  const token = localStorage.getItem("token");

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    ["chat_messages", "chat_triage", "chat_structured", "chat_session"].forEach((k) => sessionStorage.removeItem(k));
    navigate("/login");
  }, [navigate]);

  const api = useCallback(
    async (path, options) => {
      const res = await request(path, options);
      if (res.status === 401) {
        logout();
        throw new Error("Session expired");
      }
      return res;
    },
    [logout]
  );

  const loadHistory = useCallback(() => {
    api("/api/summaries")
      .then((r) => r.json())
      .then((d) => setChatHistory(d.history || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false));
  }, [api]);

  useEffect(() => {
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }
    loadHistory();
    api("/api/me")
      .then((r) => (r.ok ? r.json() : {}))
      .then(setUserData)
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist the in-progress consultation so a refresh doesn't lose it.
  useEffect(() => {
    sessionStorage.setItem("chat_session", sessionId.current);
    sessionStorage.setItem("chat_messages", JSON.stringify(messages));
    sessionStorage.setItem("chat_triage", JSON.stringify(triage));
    sessionStorage.setItem("chat_structured", JSON.stringify(structured));
  }, [messages, triage, structured]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isTyping]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => () => recogRef.current?.stop(), []);

  const add = (m) => setMessages((prev) => [...prev, { ts: Date.now(), ...m }]);

  const resizeInput = (el) => {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  };

  const sendMessage = async (override) => {
    const text = (override ?? input).trim();
    if (!text || isTyping) return;
    recogRef.current?.stop();
    add({ role: "user", text });
    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setIsTyping(true);

    try {
      const res = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId.current, message: text, language: lang }),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      add({ role: "bot", text: data.reply || "No response received." });
      if (data.triage) {
        add({ role: "bot", kind: "triage", level: data.triage.level, reason: data.triage.reason });
        setTriage(data.triage);
      }
      if (data.structured) setStructured(data.structured);
    } catch (err) {
      if (err.message !== "Session expired") {
        add({ role: "bot", kind: "error", text: t("chat.errSend") });
      }
    } finally {
      setIsTyping(false);
      inputRef.current?.focus();
    }
  };

  const runReport = async (kind) => {
    if (busyAction) return;
    if (!messages.some((m) => m.role === "user")) {
      setToast(t("chat.describeFirst"));
      return;
    }
    setBusyAction(kind);
    try {
      const res = await api(`/api/generate_${kind}?language=${lang}`, { method: "POST" });
      if (!res.ok) throw new Error();
      const data = await res.json();
      add({ role: "bot", kind, text: data[kind] || "—" });
      if (kind === "diagnosis") {
        const conditions = parseConditions(data.diagnosis);
        if (conditions.length) add({ role: "bot", kind: "doctors", conditions });
      }
      setToast(kind === "summary" ? t("chat.savedToast") : t("chat.dxToast"));
      if (kind === "summary") loadHistory();
    } catch (err) {
      if (err.message !== "Session expired") {
        add({ role: "bot", kind: "error", text: t("chat.errGen") });
      }
    } finally {
      setBusyAction(null);
    }
  };

  const toggleVoice = () => {
    if (listening) {
      recogRef.current?.stop();
      return;
    }
    const r = new SpeechRecognition();
    r.lang = meta.speech;
    r.interimResults = true;
    r.continuous = true;
    const base = input ? input.trim() + " " : "";
    r.onresult = (e) => {
      const spoken = Array.from(e.results).map((x) => x[0].transcript).join("");
      setInput(base + spoken);
      if (inputRef.current) resizeInput(inputRef.current);
    };
    r.onerror = () => setToast(t("chat.micErr"));
    r.onend = () => setListening(false);
    recogRef.current = r;
    r.start();
    setListening(true);
  };

  const exportChat = () => {
    if (!messages.length) {
      setToast(t("chat.nothing"));
      return;
    }
    const lines = messages
      .filter((m) => m.kind !== "error" && m.kind !== "doctors")
      .map((m) => {
        const who = m.role === "user" ? t("chat.you") : t("sv.doctor");
        const body = m.kind === "triage" ? `[${t("chat.triage")}: ${t(`level.${m.level}`)}] ${m.reason}` : String(m.text).replace(/\*\*/g, "");
        return `[${new Date(m.ts).toLocaleString()}] ${who}: ${body}`;
      });
    const header = `Care Companion consultation\nExported ${new Date().toLocaleString()}\n\n`;
    const url = URL.createObjectURL(new Blob([header + lines.join("\n\n")], { type: "text/plain" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `consultation-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const newChat = () => {
    recogRef.current?.stop();
    sessionId.current = newSessionId();
    setMessages([]);
    setTriage(null);
    setStructured(null);
    setShowSidebar(false);
    inputRef.current?.focus();
  };

  const initial = (userData.email || "U")[0].toUpperCase();
  const isEmergency = String(triage?.level).toLowerCase() === "emergency";

  return (
    <div className="chat-app">
      {/* ===== Sidebar ===== */}
      {showSidebar && <div className="scrim" onClick={() => setShowSidebar(false)} />}
      <aside className={`sidebar ${showSidebar ? "open" : ""}`}>
        <div className="sidebar-top">
          <Brand onClick={() => navigate("/home")} />
          <button className="icon-btn sidebar-close" onClick={() => setShowSidebar(false)} aria-label="Close menu">
            <X size={17} />
          </button>
        </div>

        <button className="btn btn-primary new-chat" onClick={newChat}>
          <Plus size={17} /> {t("chat.new")}
        </button>

        <div className="sidebar-label"><History size={14} /> {t("chat.saved")}</div>
        <div className="sidebar-list">
          {historyLoading ? (
            [1, 2, 3].map((i) => <div key={i} className="skeleton" />)
          ) : chatHistory.length === 0 ? (
            <p className="empty-note">{t("chat.none")}</p>
          ) : (
            chatHistory.map((c) => (
              <button key={c._id} className="history-item" onClick={() => navigate(`/summary/${c._id}`)}>
                <span>{String(c.summary_text).replace(/\*\*/g, "")}</span>
                <small>{c.timestamp ? new Date(c.timestamp).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : ""}</small>
              </button>
            ))
          )}
        </div>

        <div className="sidebar-user">
          <span className="user-avatar">{initial}</span>
          <div className="user-meta">
            <strong>{userData.email || "Signed in"}</strong>
            <small>{isDemo() ? t("chat.demoAcc") : t("chat.patient")}</small>
          </div>
          <button className="icon-btn" onClick={logout} aria-label={t("chat.logout")} title={t("chat.logout")}>
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* ===== Main ===== */}
      <section className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setShowSidebar(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          <div className="doctor-id">
            <img src={doctorImg} alt="" />
            <div>
              <strong>{t("sv.doctor")}</strong>
              <small><span className="online" /> {t("chat.assistant")}</small>
            </div>
          </div>
          <div className="topbar-actions">
            <button className="btn" onClick={() => runReport("summary")} disabled={!!busyAction}>
              {busyAction === "summary" ? <Loader2 size={16} className="spin" /> : <FileText size={16} />}
              <span>{t("chat.summary")}</span>
            </button>
            <button className="btn" onClick={() => runReport("diagnosis")} disabled={!!busyAction}>
              {busyAction === "diagnosis" ? <Loader2 size={16} className="spin" /> : <Stethoscope size={16} />}
              <span>{t("chat.diagnosis")}</span>
            </button>
            <LanguageSwitcher />
            <button className="icon-btn" onClick={exportChat} aria-label={t("chat.download")} title={t("chat.download")}><Download size={17} /></button>
            <button className={`icon-btn insights-btn ${showInsights ? "active" : ""}`} onClick={() => setShowInsights((v) => !v)} aria-label={t("chat.insights")} title={t("chat.insights")}><PanelRight size={17} /></button>
            <button className="icon-btn hide-sm" onClick={() => navigate("/home")} aria-label="Home" title="Home"><Home size={17} /></button>
            <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle theme" title="Toggle theme">
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </button>
          </div>
        </header>

        {isEmergency && (
          <div className="emergency-banner" role="alert">
            <Siren size={20} />
            <div>
              <strong>{t("em.title")}</strong>
              <span>{t("em.text")}</span>
            </div>
            <a href="tel:911" className="btn-call"><Phone size={15} /> {t("em.call")}</a>
          </div>
        )}

        <div className="body">
          <div className="chat-col">
            <div className="messages" ref={scrollRef}>
              <div className="messages-inner">
                {messages.length === 0 ? (
                  <div className="welcome">
                    <img src={doctorImg} alt="" />
                    <h2>{t("chat.hello")}</h2>
                    <p>{t("chat.helloText")}</p>
                    <div className="chips">
                      {SUGGESTIONS.map((k) => (
                        <button key={k} className="chip" onClick={() => sendMessage(t(k))}>{t(k)}</button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map((m, i) => <Message key={i} m={m} />)
                )}

                {isTyping && (
                  <div className="msg-row bot">
                    <img src={doctorImg} alt="" className="avatar" />
                    <div className="bubble bot typing" aria-label="Dr. Cura is typing">
                      <span /><span /><span />
                    </div>
                  </div>
                )}
              </div>
            </div>

            <footer className="composer-wrap">
              <div className={`composer ${listening ? "listening" : ""}`}>
                <textarea
                  ref={inputRef}
                  rows={1}
                  value={input}
                  placeholder={listening ? t("chat.listening") : t("chat.placeholder")}
                  onChange={(e) => { setInput(e.target.value); resizeInput(e.target); }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                />
                {SpeechRecognition && (
                  <button className={`mic ${listening ? "on" : ""}`} onClick={toggleVoice} aria-label={t("chat.voice")} title={t("chat.voice")}>
                    {listening ? <MicOff size={18} /> : <Mic size={18} />}
                  </button>
                )}
                <button className="send" onClick={() => sendMessage()} disabled={!input.trim() || isTyping} aria-label={t("chat.send")}>
                  <Send size={18} />
                </button>
              </div>
              <p className="fineprint">{t("chat.fine")}</p>
            </footer>
          </div>

          {showInsights && <Insights triage={triage} structured={structured} messages={messages} />}
        </div>
      </section>

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}
