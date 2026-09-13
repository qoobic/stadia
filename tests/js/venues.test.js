import { suite, test, assertEq, assertTrue } from './runner.js';
import {
  computeDayIndex, selectTodayVenues, todayDateString,
  getDayOffset, setDayOffset,
  normalizeForSearch, buildVenueIndex, searchVenues, venueLabel
} from '../../js/venues.js';

suite('venues.computeDayIndex');

test('launch date itself → 0', () => {
  assertEq(computeDayIndex(new Date('2026-06-01T00:00:00Z'), '2026-06-01'), 0);
});

test('next UTC day → 1', () => {
  assertEq(computeDayIndex(new Date('2026-06-02T00:00:00Z'), '2026-06-01'), 1);
});

test('mid-day on launch → still 0', () => {
  assertEq(computeDayIndex(new Date('2026-06-01T23:59:59Z'), '2026-06-01'), 0);
});

test('30 days later → 30', () => {
  assertEq(computeDayIndex(new Date('2026-07-01T12:00:00Z'), '2026-06-01'), 30);
});

test('before launch → 0 (clamps non-negative)', () => {
  assertEq(computeDayIndex(new Date('2026-05-15T00:00:00Z'), '2026-06-01'), 0);
});

suite('venues.selectTodayVenues');

const fixture = {
  launchDate: '2026-06-01',
  l1: [{ id: 'a0' }, { id: 'a1' }, { id: 'a2' }],
  l2: [{ id: 'b0' }, { id: 'b1' }, { id: 'b2' }, { id: 'b3' }],
  l3: [{ id: 'c0' }, { id: 'c1' }, { id: 'c2' }, { id: 'c3' }, { id: 'c4' }],
  l4: [{ id: 'd0' }, { id: 'd1' }, { id: 'd2' }, { id: 'd3' }, { id: 'd4' }, { id: 'd5' }],
  l5: [{ id: 'e0' }, { id: 'e1' }, { id: 'e2' }, { id: 'e3' }, { id: 'e4' }, { id: 'e5' }, { id: 'e6' }]
};

test('day 0 picks slot 0 from each band', () => {
  assertEq(selectTodayVenues(0, fixture).map(v => v.id), ['a0', 'b0', 'c0', 'd0', 'e0']);
});

test('day 1 rotates each band by 1', () => {
  assertEq(selectTodayVenues(1, fixture).map(v => v.id), ['a1', 'b1', 'c1', 'd1', 'e1']);
});

test('day 3 wraps l1 (length 3) back to a0; others continue', () => {
  assertEq(selectTodayVenues(3, fixture).map(v => v.id), ['a0', 'b3', 'c3', 'd3', 'e3']);
});

test('deterministic — same day twice yields the same venues', () => {
  assertEq(selectTodayVenues(42, fixture).map(v => v.id), selectTodayVenues(42, fixture).map(v => v.id));
});

test('an empty band throws, naming the band', () => {
  let msg = '';
  try { selectTodayVenues(0, { ...fixture, l3: [] }); } catch (e) { msg = e.message; }
  assertTrue(msg.includes('l3'), `expected the error to name band l3, got "${msg}"`);
});

suite('venues.todayDateString');

test('formats as YYYY-MM-DD in UTC', () => {
  assertEq(todayDateString(new Date('2026-06-01T12:34:56Z')), '2026-06-01');
});

test('zero-pads month and day', () => {
  assertEq(todayDateString(new Date('2026-01-05T00:00:00Z')), '2026-01-05');
});

suite('venues.dayOffset');

test('default offset is 0 when nothing saved', () => {
  localStorage.removeItem('stadia_dayOffset');
  assertEq(getDayOffset(), 0);
});

test('setDayOffset(0) clears the key', () => {
  setDayOffset(5);
  setDayOffset(0);
  assertEq(localStorage.getItem('stadia_dayOffset'), null);
});

test('setDayOffset round-trips non-zero values', () => {
  setDayOffset(7);
  assertEq(getDayOffset(), 7);
  setDayOffset(-3);
  assertEq(getDayOffset(), -3);
  setDayOffset(0);
});

suite('venues.normalizeForSearch');

test('lowercases', () => {
  assertEq(normalizeForSearch('Anfield'), 'anfield');
});

test('strips diacritics (NFD + combining marks)', () => {
  assertEq(normalizeForSearch('Maracanã'), 'maracana');
  assertEq(normalizeForSearch('Santiago Bernabéu'), 'santiago bernabeu');
  assertEq(normalizeForSearch('Estádio do Café'), 'estadio do cafe');
});

test('collapses whitespace and trims', () => {
  assertEq(normalizeForSearch('  Old   Trafford  '), 'old trafford');
});

suite('venues.buildVenueIndex / searchVenues');

const sample = {
  launchDate: '2026-06-01',
  l1: [
    { id: 'anfield', name: 'Anfield', city: 'Liverpool', country: 'England', aliases: [], lat: 53.4308, lng: -2.9609, zoom: 16 },
    { id: 'camp-nou', name: 'Spotify Camp Nou', city: 'Barcelona', country: 'Spain', aliases: ['Camp Nou', 'Nou Camp'], lat: 41.3809, lng: 2.1228, zoom: 16 }
  ],
  l2: [
    { id: 'maracana', name: 'Maracanã', city: 'Rio de Janeiro', country: 'Brazil', aliases: [], lat: -22.9121, lng: -43.2302, zoom: 16 }
  ],
  l3: [
    { id: 'mcg', name: 'Melbourne Cricket Ground', city: 'Melbourne', country: 'Australia', aliases: ['MCG'], lat: -37.82, lng: 144.9834, zoom: 16 }
  ],
  l4: [],
  l5: []
};

test('index pools venues from every band', () => {
  assertEq(buildVenueIndex(sample).length, 4);
});

test('search by name (case-insensitive)', () => {
  assertEq(searchVenues(buildVenueIndex(sample), 'ANF').map(v => v.id), ['anfield']);
});

test('search ignores diacritics', () => {
  assertEq(searchVenues(buildVenueIndex(sample), 'maracana').map(v => v.id), ['maracana']);
});

test('search matches "name, city" when the query includes the city', () => {
  assertEq(searchVenues(buildVenueIndex(sample), 'anfield, liver').map(v => v.id), ['anfield']);
});

test('empty query returns []', () => {
  const idx = buildVenueIndex(sample);
  assertEq(searchVenues(idx, ''), []);
  assertEq(searchVenues(idx, '   '), []);
});

test('internal search fields are not leaked to callers', () => {
  const r = searchVenues(buildVenueIndex(sample), 'anfield')[0];
  assertTrue(!('_name' in r) && !('_full' in r) && !('_aliases' in r), 'search results must not expose _name/_full/_aliases');
});

test('returns all matches (no cap)', () => {
  const big = { l1: [], l2: [], l3: [], l4: [], l5: [] };
  for (let i = 0; i < 20; i++) {
    big.l1.push({ id: `v${i}`, name: `Stadium${i}`, city: 'X', country: 'Y', aliases: [] });
  }
  assertEq(searchVenues(buildVenueIndex(big), 'stadium').length, 20);
});

test('name prefix ranks above a substring match', () => {
  const data = {
    l1: [
      { id: 'oval',    name: 'The Oval',       city: 'London',  country: 'England', aliases: [] },
      { id: 'ovalie',  name: 'Stade Ovalie',   city: 'Toulouse', country: 'France', aliases: [] }
    ],
    l2: [], l3: [], l4: [], l5: []
  };
  assertEq(searchVenues(buildVenueIndex(data), 'stade ovalie')[0].id, 'ovalie');
});

suite('venues.searchVenues — aliases');

test('a venue is findable by an alias', () => {
  assertEq(searchVenues(buildVenueIndex(sample), 'MCG').map(v => v.id), ['mcg']);
});

test('alias search is diacritic- and case-insensitive', () => {
  assertEq(searchVenues(buildVenueIndex(sample), 'nou camp').map(v => v.id), ['camp-nou']);
});

test('a name prefix outranks an alias prefix', () => {
  const data = {
    l1: [
      { id: 'real', name: 'Camp Nou Stadium', city: 'Nowhere', country: 'X', aliases: [] },
      { id: 'alias', name: 'Some Other Ground', city: 'Elsewhere', country: 'Y', aliases: ['Camp Nou'] }
    ],
    l2: [], l3: [], l4: [], l5: []
  };
  assertEq(searchVenues(buildVenueIndex(data), 'camp nou')[0].id, 'real');
});

test('a missing aliases field does not break the index', () => {
  const data = { l1: [{ id: 'x', name: 'No Aliases Ground', city: 'C', country: 'D' }], l2: [], l3: [], l4: [], l5: [] };
  assertEq(searchVenues(buildVenueIndex(data), 'no aliases').map(v => v.id), ['x']);
});

test('an empty aliases array does not break the index (the export ships these)', () => {
  const data = { l1: [{ id: 'y', name: 'Empty Aliases Ground', city: 'C', country: 'D', aliases: [] }], l2: [], l3: [], l4: [], l5: [] };
  assertEq(searchVenues(buildVenueIndex(data), 'empty aliases').map(v => v.id), ['y']);
});

suite('venues.venueLabel');

test('labels a venue as "name, city"', () => {
  assertEq(venueLabel({ name: 'Anfield', city: 'Liverpool', country: 'England' }), 'Anfield, Liverpool');
});
