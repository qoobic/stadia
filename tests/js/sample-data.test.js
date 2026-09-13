import { suite, test, assertTrue, assertEq } from './runner.js';
import { loadVenuesData, buildVenueIndex, selectTodayVenues } from '../../js/venues.js';

const BANDS = ['l1', 'l2', 'l3', 'l4', 'l5'];
const CLASSES = ['stadium', 'arena', 'circuit', 'racecourse', 'golf'];

// Loaded once before the suite is registered; test.html awaits this module.
const data = await loadVenuesData('../../data/sample-venues.json');
const all = BANDS.flatMap(b => data[b] || []);

suite('sample-data');

test('declares a launchDate as YYYY-MM-DD', () => {
  assertTrue(/^\d{4}-\d{2}-\d{2}$/.test(data.launchDate), `bad launchDate: ${data.launchDate}`);
});

test('is still flagged as temporary placeholder data', () => {
  assertEq(data._temporary, true);
  assertTrue(typeof data._warning === 'string' && data._warning.length > 0, 'temporary data must carry a _warning');
});

test('every band is present and non-empty', () => {
  for (const b of BANDS) {
    assertTrue(Array.isArray(data[b]) && data[b].length > 0, `band ${b} must be a non-empty array`);
  }
});

test('every venue id is unique across all bands', () => {
  const ids = all.map(v => v.id);
  const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
  assertEq(dupes, []);
});

test('every venue carries the required fields', () => {
  for (const v of all) {
    for (const f of ['id', 'venueId', 'name', 'city', 'country', 'venueClass', 'lat', 'lng', 'zoom']) {
      assertTrue(v[f] !== undefined && v[f] !== '', `${v.id || '(no id)'} is missing ${f}`);
    }
  }
});

test('every venueId looks like a catalogue venue_id', () => {
  for (const v of all) {
    assertTrue(/^[a-z0-9-]+$/.test(v.venueId), `${v.id}: venueId "${v.venueId}" is not a catalogue-style slug`);
  }
});

test('coordinates are in range and not null island', () => {
  for (const v of all) {
    assertTrue(typeof v.lat === 'number' && v.lat >= -90 && v.lat <= 90, `${v.id}: lat out of range`);
    assertTrue(typeof v.lng === 'number' && v.lng >= -180 && v.lng <= 180, `${v.id}: lng out of range`);
    assertTrue(!(v.lat === 0 && v.lng === 0), `${v.id}: coordinates are 0,0`);
  }
});

test('zoom is an integer tight enough to frame a venue', () => {
  for (const v of all) {
    assertTrue(Number.isInteger(v.zoom), `${v.id}: zoom must be an integer`);
    assertTrue(v.zoom >= 12 && v.zoom <= 18, `${v.id}: zoom ${v.zoom} is outside 12–18`);
  }
});

test('venueClass is one of the five catalogue classes', () => {
  for (const v of all) {
    assertTrue(CLASSES.includes(v.venueClass), `${v.id}: unknown venueClass "${v.venueClass}"`);
  }
});

test('aliases, where present, are an array of non-empty strings', () => {
  for (const v of all) {
    if (v.aliases === undefined) continue;
    assertTrue(Array.isArray(v.aliases), `${v.id}: aliases must be an array`);
    for (const a of v.aliases) {
      assertTrue(typeof a === 'string' && a.trim().length > 0, `${v.id}: empty alias`);
    }
  }
});

test('at least one venue has a populated alias, so the alias path is exercised', () => {
  assertTrue(all.some(v => Array.isArray(v.aliases) && v.aliases.length > 0), 'no venue has aliases');
});

test('the index pools every venue', () => {
  assertEq(buildVenueIndex(data).length, all.length);
});

test('a year of days always selects five real venues', () => {
  for (let d = 0; d < 365; d++) {
    const picks = selectTodayVenues(d, data);
    assertEq(picks.length, 5);
    assertTrue(picks.every(p => p && p.id), `day ${d} produced a hole`);
  }
});
