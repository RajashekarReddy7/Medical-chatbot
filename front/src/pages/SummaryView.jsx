import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, FileText, Stethoscope, User, AlertCircle, Sun, Moon, Printer } from "lucide-react";
import Brand from "../components/Brand";
import useTheme from "../components/useTheme";
import LanguageSwitcher from "../components/LanguageSwitcher";
import { useI18n } from "../i18n";
import RichText from "../components/RichText";
import { request } from "../api";
import "../styles/summaryView.css";

export default function SummaryView() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t, lang } = useI18n();
  const [theme, toggleTheme] = useTheme();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const token = localStorage.getItem("token");

  useEffect(() => {
    if (!token) {
      navigate("/login", { replace: true });
      return;
    }
    request(`/api/summaries/${id}`)
      .then((res) => {
        if (res.status === 401) {
          localStorage.removeItem("token");
          navigate("/login", { replace: true });
          throw new Error("unauthorized");
        }
        if (!res.ok) throw new Error("not found");
        return res.json();
      })
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const date = data?.timestamp
    ? new Date(data.timestamp).toLocaleString(lang, { dateStyle: "long", timeStyle: "short" })
    : "";

  return (
    <div className="sv">
      <header className="sv-header">
        <div className="sv-container sv-header-inner">
          <button className="btn btn-ghost" onClick={() => navigate("/chat")}>
            <ArrowLeft size={17} className="flip-rtl" /> {t("sv.backChat")}
          </button>
          <Brand />
          <div className="sv-actions">
            <LanguageSwitcher />
            <button className="icon-btn" onClick={() => window.print()} aria-label="Print"><Printer size={16} /></button>
            <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </button>
          </div>
        </div>
      </header>

      <main className="sv-container sv-main">
        {loading ? (
          <div className="sv-card"><div className="sv-skel w60" /><div className="sv-skel" /><div className="sv-skel" /><div className="sv-skel w40" /></div>
        ) : !data ? (
          <div className="sv-card sv-empty">
            <AlertCircle size={30} />
            <h2>{t("sv.notFound")}</h2>
            <p>{t("sv.notFoundText")}</p>
            <button className="btn btn-primary" onClick={() => navigate("/chat")}>{t("sv.backChat")}</button>
          </div>
        ) : (
          <>
            <div className="sv-title">
              <h1>{t("sv.title")}</h1>
              {date && <span>{date}</span>}
            </div>

            <section className="sv-card">
              <h2><FileText size={18} /> {t("sv.summary")}</h2>
              <div className="sv-text">
                <RichText text={data.summary_text} />
              </div>
            </section>

            {data.conversation?.length > 0 && (
              <section className="sv-card">
                <h2><Stethoscope size={18} /> {t("sv.convo")}</h2>
                <div className="sv-convo">
                  {data.conversation.map((m, i) => (
                    <div key={i} className={`sv-msg ${m.role === "doctor" ? "doctor" : "patient"}`}>
                      <span className="sv-who">
                        {m.role === "doctor" ? <Stethoscope size={14} /> : <User size={14} />}
                        {m.role === "doctor" ? t("sv.doctor") : t("chat.you")}
                      </span>
                      <p>{m.message}</p>
                    </div>
                  ))}
                </div>
              </section>
            )}

            <p className="sv-note">{t("sv.note")}</p>
          </>
        )}
      </main>
    </div>
  );
}
