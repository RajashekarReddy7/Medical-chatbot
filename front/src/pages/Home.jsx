import { useNavigate } from "react-router-dom";
import { ShieldAlert, Clock, Languages, FileText, Stethoscope, ArrowRight, Sun, Moon, CheckCircle2, MapPin, Siren } from "lucide-react";
import Brand from "../components/Brand";
import LanguageSwitcher from "../components/LanguageSwitcher";
import useTheme from "../components/useTheme";
import { useI18n } from "../i18n";
import heroImg from "../assets/doctor1.jpg";
import "../styles/home.css";

const FEATURES = [
  { icon: ShieldAlert, key: "f1" },
  { icon: Stethoscope, key: "f2" },
  { icon: MapPin, key: "f3" },
  { icon: Languages, key: "f4" },
  { icon: FileText, key: "f5" },
  { icon: Clock, key: "f6" },
];

export default function Home() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const [theme, toggleTheme] = useTheme();
  const loggedIn = !!localStorage.getItem("token");
  const start = () => navigate(loggedIn ? "/chat" : "/login");

  return (
    <div className="home">
      <header className="home-header">
        <div className="home-container home-header-inner">
          <Brand />
          <div className="home-actions">
            <LanguageSwitcher />
            <button className="icon-btn" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
            </button>
            <button className="btn" onClick={start}>
              {loggedIn ? t("openChat") : t("signIn")}
            </button>
          </div>
        </div>
      </header>

      <main>
        <section className="hero home-container">
          <div className="hero-copy">
            <span className="pill"><span className="pill-dot" /> {t("home.badge")}</span>
            <h1>{t("home.title1")} <em>{t("home.title2")}</em></h1>
            <p>{t("home.text")}</p>
            <div className="hero-cta">
              <button className="btn btn-primary btn-lg" onClick={start}>
                {t("home.cta")} <ArrowRight size={18} className="flip-rtl" />
              </button>
            </div>
            <ul className="hero-points">
              <li><CheckCircle2 size={16} /> {t("home.p1")}</li>
              <li><CheckCircle2 size={16} /> {t("home.p2")}</li>
              <li><CheckCircle2 size={16} /> {t("home.p3")}</li>
            </ul>
          </div>

          <div className="hero-visual">
            <img src={heroImg} alt="" />
            <div className="float-card float-card-top">
              <Siren size={18} className="warn-ic" />
              <div><strong>{t("home.floatTitle")}</strong><small>{t("home.floatSub")}</small></div>
            </div>
            <div className="float-card float-card-bottom">
              <MapPin size={18} />
              <div><strong>{t("home.floatTitle2")}</strong><small>{t("home.floatSub2")}</small></div>
            </div>
          </div>
        </section>

        <section className="home-container features">
          <h2>{t("home.featuresTitle")}</h2>
          <div className="feature-grid">
            {FEATURES.map(({ icon: Icon, key }) => (
              <article className="feature" key={key}>
                <span className="feature-icon"><Icon size={20} /></span>
                <h3>{t(`home.${key}t`)}</h3>
                <p>{t(`home.${key}d`)}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="home-container">
          <div className="disclaimer">
            <ShieldAlert size={18} />
            <p><strong>{t("home.discStrong")}</strong> {t("home.disc")}</p>
          </div>
        </section>
      </main>

      <footer className="home-footer">
        <div className="home-container">© {new Date().getFullYear()} Care Companion · {t("home.footer")}</div>
      </footer>
    </div>
  );
}
