import { suite, test, assertEq } from './runner.js';
import {
  initState, freshTodayState, loadToday, saveToday,
  recordRoundResult, markCompleted, loadDay, clearDay,
  _resetForTesting
} from '../../js/state.js';

function clear() {
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith('stadia_')) localStorage.removeItem(key);
  }
  _resetForTesting();
}

function setup(dayIndex = 0) {
  clear();
  initState(dayIndex);
}

suite('state.freshTodayState');

test('fresh state has empty rounds, not completed', () => {
  const s = freshTodayState('2026-06-01', 0);
  assertEq(s.date, '2026-06-01');
  assertEq(s.dayIndex, 0);
  assertEq(s.rounds, []);
  assertEq(s.completed, false);
  assertEq(s.totalScore, 0);
});

suite('state.loadToday');

test('returns null when nothing saved', () => {
  setup(0);
  assertEq(loadToday(), null);
});

test('round-trips a saved state', () => {
  setup(0);
  const s = freshTodayState('2026-06-01', 0);
  s.rounds.push({ targetId: 'paris', pickId: 'lyon', distKm: 390, score: 76, multiplier: 1 });
  saveToday(s);
  const loaded = loadToday();
  assertEq(loaded.rounds.length, 1);
  assertEq(loaded.rounds[0].targetId, 'paris');
});

suite('state.recordRoundResult');

test('appends to rounds and updates totalScore', () => {
  setup(0);
  saveToday(freshTodayState('2026-06-01', 0));
  recordRoundResult({ targetId: 'a', pickId: 'x', distKm: 10, score: 100, multiplier: 1 });
  recordRoundResult({ targetId: 'b', pickId: 'y', distKm: 50, score: 196, multiplier: 2 });
  const s = loadToday();
  assertEq(s.rounds.length, 2);
  assertEq(s.totalScore, 296);
});

suite('state.markCompleted');

test('sets completed: true', () => {
  setup(0);
  saveToday(freshTodayState('2026-06-01', 0));
  markCompleted();
  assertEq(loadToday().completed, true);
});

suite('state.loadDay / clearDay');

test('loadDay returns state saved under that day index', () => {
  setup(5);
  saveToday(freshTodayState('2026-06-06', 5));
  assertEq(loadDay(5).dayIndex, 5);
});

test('loadDay returns null for a day with no state', () => {
  setup(0);
  assertEq(loadDay(99), null);
});

test('clearDay removes that day only', () => {
  clear();
  initState(1); saveToday(freshTodayState('d1', 1));
  initState(2); saveToday(freshTodayState('d2', 2));
  clearDay(1);
  assertEq(loadDay(1), null);
  assertEq(loadDay(2).dayIndex, 2);
});
