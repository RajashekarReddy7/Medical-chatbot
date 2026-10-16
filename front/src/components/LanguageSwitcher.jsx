import { Globe } from "lucide-react";
import { LANGUAGES, useI18n } from "../i18n";

export default function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();
  return (
    <label className="lang-switch" title={t("language")}>
      <Globe size={16} />
      <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label={t("language")}>
        {LANGUAGES.map((l) => (
          <option key={l.code} value={l.code}>{l.native}</option>
        ))}
      </select>
    </label>
  );
}
