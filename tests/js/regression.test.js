import { suite, test, assertEq } from './runner.js';
import {
  initState, freshTodayState, saveToday,
  recordRoundResult, markCompleted, loadToday, _resetForTesting
} from '../../js/state.js';

function setup(dayIndex = 6) {
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith('stadia_')) localStorage.removeItem(key);
  }
  _resetForTesting();
  initState(dayIndex);
  saveToday(freshTodayState('2026-05-30', dayIndex));
}

suite('regression.recordRoundResult (multi-session safety)');

test('re-recording the same roundIndex is ignored (the 1200/1000 bug)', () => {
  setup();
  recordRoundResult({ roundIndex: 0, score: 100, multiplier: 1, targetId: 'a', pickId: 'a', distKm: 0 });
  recordRoundResult({ roundIndex: 1, score: 100, multiplier: 1, targetId: 'b', pickId: 'b', distKm: 0 });
  recordRoundResult({ roundIndex: 2, score: 200, multiplier: 2, targetId: 'c', pickId: 'c', distKm: 0 });
  recordRoundResult({ roundIndex: 2, score: 200, multiplier: 2, targetId: 'c', pickId: 'c', distKm: 0 });
  recordRoundResult({ roundIndex: 3, score: 300, multiplier: 3, targetId: 'd', pickId: 'd', distKm: 0 });
  recordRoundResult({ roundIndex: 4, score: 300, multiplier: 3, targetId: 'e', pickId: 'e', distKm: 0 });
  const s = loadToday();
  assertEq(s.rounds.length, 5);
  assertEq(s.totalScore, 1000);
});

test('writes after completion are ignored', () => {
  setup();
  recordRoundResult({ roundIndex: 0, score: 50, multiplier: 1, targetId: 'a', pickId: 'x', distKm: 0 });
  markCompleted();
  recordRoundResult({ roundIndex: 1, score: 99, multiplier: 1, targetId: 'b', pickId: 'y', distKm: 0 });
  assertEq(loadToday().rounds.length, 1);
});

test('rounds are hard-capped at 5 even with novel indices', () => {
  setup();
  for (let i = 0; i < 7; i++) {
    recordRoundResult({ roundIndex: i, score: 10, multiplier: 1, targetId: 'c' + i, pickId: 'c' + i, distKm: 0 });
  }
  assertEq(loadToday().rounds.length, 5);
});

test('legacy calls without roundIndex still append by position', () => {
  setup();
  recordRoundResult({ targetId: 'a', pickId: 'x', distKm: 10, score: 100, multiplier: 1 });
  recordRoundResult({ targetId: 'b', pickId: 'y', distKm: 50, score: 196, multiplier: 2 });
  const s = loadToday();
  assertEq(s.rounds.length, 2);
  assertEq(s.totalScore, 296);
});
