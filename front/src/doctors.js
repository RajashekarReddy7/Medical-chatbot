/* Turn the diagnosis text into a ranked list of conditions, and map each one to
   the kind of specialist you would search for on Google Maps. */

const SPECIALTIES = [
  ["General physician", /viral|\bflu\b|influenza|common cold|fatigue|an(a)?emia|fever/],
  ["Cardiologist", /cardi|heart|angina|myocard|arrhythm|coronary|hypertens/],
  ["Pulmonologist", /pulmon|pneumon|asthma|bronch|copd|lung|respirat|tubercul/],
  ["Neurologist", /migraine|neuro|stroke|epilep|seizure|mening|headache|vertigo|parkinson/],
  ["Gastroenterologist", /gastr|ulcer|gerd|reflux|appendic|hepat|colitis|ibs|bowel|pancrea|gallbladder|stomach|food poison/],
  ["Dermatologist", /skin|dermat|eczema|psoria|rash|acne|urticaria|hives|fung/],
  ["Urologist", /urinar|uti\b|kidney|renal|cystitis|prostat|bladder/],
  ["Orthopedic doctor", /arthrit|back|musculo|spine|spinal|fracture|sprain|strain|joint|sciatica|disc\b|tendon/],
  ["Endocrinologist", /diabet|thyroid|hormon|endocrin|adrenal/],
  ["Psychiatrist", /anxiety|depress|panic|psychi|bipolar|stress disorder/],
  ["ENT specialist", /\bear\b|throat|sinus|tonsil|otitis|pharyng|laryng|rhinit/],
  ["Ophthalmologist", /\beye\b|conjunctiv|vision|glaucoma|cataract/],
];

export const specialtyFor = (disease) =>
  SPECIALTIES.find(([, re]) => re.test(String(disease).toLowerCase()))?.[0] || "General physician";

/* "1. **Migraine** — reason" / "1) Migraine: reason" / "Migraine - reason" -> ["Migraine", ...] */
export function parseConditions(text) {
  const lines = String(text || "").replace(/\*\*/g, "").split("\n").map((l) => l.trim()).filter(Boolean);
  const numbered = lines.filter((l) => /^\d+\s*[.)]\s*\S/.test(l));
  const source = numbered.length ? numbered : lines.slice(0, 1);
  const names = source
    .map((l) => l.replace(/^\d+\s*[.)]\s*/, "").split(/\s[—–-]\s|:|\(/)[0].trim())
    .filter((n) => n && n.length < 80);
  return [...new Set(names)].slice(0, 5).map((name) => ({ name, specialty: specialtyFor(name) }));
}

const enc = encodeURIComponent;

/* Keyless Google Maps embed + deep links. */
export function mapsUrls({ specialty, coords, place, lang }) {
  const near = coords ? `${coords.lat},${coords.lng}` : place;
  const query = `${specialty} near ${near}`;
  return {
    embed: `https://maps.google.com/maps?q=${enc(query)}&z=13&hl=${lang}&output=embed`,
    open: `https://www.google.com/maps/search/?api=1&query=${enc(query)}`,
  };
}
