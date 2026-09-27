const MS_PER_DAY = 86_400_000;
const DAY_OFFSET_KEY = 'stadia_dayOffset';
const BANDS = ['l1', 'l2', 'l3', 'l4', 'l5'];

export function computeDayIndex(now, launchDateIso) {
  const launch = Date.parse(`${launchDateIso}T00:00:00Z`);
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Math.max(0, Math.floor((today - launch) / MS_PER_DAY));
}

export function getDayOffset() {
  try {
    const raw = localStorage.getItem(DAY_OFFSET_KEY);
    const n = raw === null ? 0 : parseInt(raw, 10);
    return Number.isFinite(n) ? n : 0;
  } catch (_) { return 0; }
}

export function setDayOffset(n) {
  try {
    if (n === 0) localStorage.removeItem(DAY_OFFSET_KEY);
    else localStorage.setItem(DAY_OFFSET_KEY, String(n));
  } catch (_) {}
}

export function selectTodayVenues(dayIndex, venuesData) {
  return BANDS.map(key => {
    const list = venuesData[key];
    if (!list || list.length === 0) throw new Error(`venue data band "${key}" is empty`);
    return list[dayIndex % list.length];
  });
}

export async function loadVenuesData(url = 'data/live-venues.json') {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: HTTP ${res.status}`);
  return res.json();
}

export function todayDateString(now) {
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth() + 1).padStart(2, '0');
  const d = String(now.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

export function normalizeForSearch(s) {
  return String(s)
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .trim();
}

export function venueLabel(venue) {
  return `${venue.name}, ${venue.city}`;
}

export function buildVenueIndex(venuesData) {
  const all = [];
  for (const key of BANDS) {
    for (const venue of venuesData[key] || []) {
      const aliases = Array.isArray(venue.aliases) ? venue.aliases : [];
      all.push({
        ...venue,
        _name: normalizeForSearch(venue.name),
        _full: normalizeForSearch(`${venue.name}, ${venue.city}, ${venue.country}`),
        _aliases: aliases.map(normalizeForSearch)
      });
    }
  }
  return all;
}

export function searchVenues(index, query) {
  const q = normalizeForSearch(query);
  if (!q) return [];
  const results = [];
  for (const venue of index) {
    const rank = matchRank(venue, q);
    if (rank !== null) results.push({ venue, rank });
  }
  results.sort((a, b) => a.rank - b.rank || a.venue._name.localeCompare(b.venue._name));
  return results.map(({ venue: { _name, _full, _aliases, ...rest } }) => rest);
}

function matchRank(venue, q) {
  if (venue._name.startsWith(q) || venue._full.startsWith(q)) return 0;
  if (venue._aliases.some(a => a.startsWith(q))) return 1;
  if (venue._name.includes(q) || venue._full.includes(q)) return 2;
  if (venue._aliases.some(a => a.includes(q))) return 3;
  return null;
}
