import { useState } from "react";
import { MapPin, Navigation, Search, ExternalLink, Loader2, Stethoscope } from "lucide-react";
import { mapsUrls } from "../doctors";
import { useI18n } from "../i18n";
import "../styles/doctors.css";

export default function NearbyDoctors({ conditions }) {
  const { t, lang } = useI18n();
  const [active, setActive] = useState(0);
  const [coords, setCoords] = useState(null);
  const [place, setPlace] = useState("");
  const [query, setQuery] = useState(""); // submitted city text
  const [status, setStatus] = useState("idle"); // idle | locating | denied

  const current = conditions[active];
  const hasLocation = !!coords || !!query;
  const urls = hasLocation ? mapsUrls({ specialty: current.specialty, coords, place: query, lang }) : null;
  const spec = t(`spec.${current.specialty}`);

  const locate = () => {
    if (!navigator.geolocation) return setStatus("denied");
    setStatus("locating");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude.toFixed(5), lng: pos.coords.longitude.toFixed(5) });
        setQuery("");
        setStatus("idle");
      },
      () => setStatus("denied"),
      { timeout: 10000 }
    );
  };

  const submitPlace = (e) => {
    e.preventDefault();
    if (!place.trim()) return;
    setQuery(place.trim());
    setCoords(null);
    setStatus("idle");
  };

  return (
    <div className="msg-row bot">
      <div className="avatar-spacer" />
      <div className="doctors">
        <header>
          <MapPin size={17} />
          <div>
            <strong>{t("doc.title")}</strong>
            <small>{t("doc.sub")}</small>
          </div>
        </header>

        <div className="doc-body">
          <div className="doc-top">
            <span className="doc-ic"><Stethoscope size={18} /></span>
            <div>
              <small>{active === 0 ? t("doc.mostLikely") : t("doc.others")}</small>
              <strong>{current.name}</strong>
              <em>{t("doc.specialist")}: {spec}</em>
            </div>
          </div>

          {conditions.length > 1 && (
            <div className="cond-tabs" role="tablist">
              {conditions.map((c, i) => (
                <button key={c.name} role="tab" aria-selected={i === active}
                  className={`cond-tab ${i === active ? "on" : ""}`} onClick={() => setActive(i)}>
                  {c.name}
                </button>
              ))}
            </div>
          )}

          <div className="loc-row">
            <button className="btn btn-primary" onClick={locate} disabled={status === "locating"}>
              {status === "locating" ? <Loader2 size={16} className="spin" /> : <Navigation size={16} />}
              {status === "locating" ? t("doc.locating") : t("doc.useLoc")}
            </button>
            <form className="place-form" onSubmit={submitPlace}>
              <input value={place} onChange={(e) => setPlace(e.target.value)} placeholder={t("doc.orCity")} aria-label={t("doc.orCity")} />
              <button type="submit" aria-label={t("doc.search")}><Search size={16} /></button>
            </form>
          </div>
          {status === "denied" && <p className="doc-warn">{t("doc.denied")}</p>}

          {urls ? (
            <>
              <iframe key={urls.embed} className="map" src={urls.embed} title={`${spec} map`} loading="lazy"
                referrerPolicy="no-referrer-when-downgrade" allowFullScreen />
              <a className="btn open-maps" href={urls.open} target="_blank" rel="noreferrer">
                <ExternalLink size={15} /> {t("doc.open")}
              </a>
            </>
          ) : (
            <div className="map-empty"><MapPin size={26} /><p>{t("doc.prompt", { spec })}</p></div>
          )}
          <p className="doc-disc">{t("doc.disc")}</p>
        </div>
      </div>
    </div>
  );
}

