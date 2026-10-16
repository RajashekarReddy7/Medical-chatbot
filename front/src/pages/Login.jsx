import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Mail, Lock, AlertCircle, CheckCircle2, ArrowLeft, Sun, Moon, Sparkles } from "lucide-react";
import Brand from "../components/Brand";
import LanguageSwitcher from "../components/LanguageSwitcher";
import useTheme from "../components/useTheme";
import { useI18n } from "../i18n";
import { login, register, DEMO } from "../api";
import loginImage from "../assets/doctor1.jpg";
import "../styles/login.css";

export default function Login() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [theme, toggleTheme] = useTheme();
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState(null); // { type: "error" | "success", text }

  const switchMode = () => {
    setIsLogin((v) => !v);
    setNotice(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setNotice(null);
    if (!isLogin && password.length < 6) {
      setNotice({ type: "error", text: t("login.errPass") });
      return;
    }
    setLoading(true);

    try {
      if (isLogin) {
        const r = await login(email, password);
        if (r.ok) {
          localStorage.setItem("token", r.token);
          navigate("/chat");
        } else {
          setNotice({ type: "error", text: r.error });
        }
      } else {
        const r = await register(email, password);
        if (r.ok) {
          setIsLogin(true);
          setPassword("");
          setNotice({ type: "success", text: t("login.created") });
        } else {
          setNotice({ type: "error", text: r.error });
        }
      }
    } catch {
      setNotice({ type: "error", text: t("login.errNet") });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth">
      <aside className="auth-visual" style={{ backgroundImage: `url(${loginImage})` }}>
        <div className="auth-visual-overlay">
          <h2>{t("login.tag1")} <br />{t("login.tag2")}</h2>
          <p>{t("login.tagText")}</p>
        </div>
      </aside>

      <main className="auth-panel">
        <div className="auth-top">
          <button className="btn btn-ghost" onClick={() => navigate("/home")}>
            <ArrowLeft size={16} className="flip-rtl" /> {t("back")}
          </button>
          <div className="auth-tools">
            <LanguageSwitcher />
            <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </button>
          </div>
        </div>

        <div className="auth-card">
          <Brand />
          <h1>{isLogin ? t("login.welcome") : t("login.create")}</h1>
          <p className="auth-sub">{isLogin ? t("login.subIn") : t("login.subUp")}</p>

          {notice && (
            <div className={`notice notice-${notice.type}`} role="alert">
              {notice.type === "error" ? <AlertCircle size={17} /> : <CheckCircle2 size={17} />}
              {notice.text}
            </div>
          )}

          {isLogin && (
            <button
              type="button"
              className="demo-box"
              onClick={() => { setEmail(DEMO.email); setPassword(DEMO.password); setNotice(null); }}
            >
              <Sparkles size={17} />
              <span>
                <strong>{t("login.demo")}</strong>
                <small dir="ltr">{DEMO.email} · {DEMO.password}</small>
              </span>
              <em>{t("login.autofill")}</em>
            </button>
          )}

          <form onSubmit={handleSubmit}>
            <label className="field">
              <span>{t("login.email")}</span>
              <div className="input-wrap">
                <Mail size={17} />
                <input type="email" dir="ltr" placeholder="you@example.com" value={email}
                  onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
              </div>
            </label>

            <label className="field">
              <span>{t("login.password")}</span>
              <div className="input-wrap">
                <Lock size={17} />
                <input type={showPassword ? "text" : "password"} dir="ltr" placeholder={t("login.passPh")} value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={isLogin ? "current-password" : "new-password"} required />
                <button type="button" className="eye" onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}>
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </label>

            <button type="submit" className="btn btn-primary btn-lg submit" disabled={loading}>
              {loading ? <span className="spinner" /> : isLogin ? t("signIn") : t("login.submitUp")}
            </button>
          </form>

          <p className="auth-switch">
            {isLogin ? t("login.newTo") : t("login.haveAcc")}{" "}
            <button type="button" onClick={switchMode}>{isLogin ? t("login.createLink") : t("signIn")}</button>
          </p>
        </div>
      </main>
    </div>
  );
}
