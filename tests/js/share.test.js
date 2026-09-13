import { suite, test, assertEq } from './runner.js';
import { scoreBand, buildShareString } from '../../js/share.js';

suite('share.scoreBand');

test('100/100 → 🎯 (perfect)', () => assertEq(scoreBand(100, 100), '🎯'));
test('300/300 → 🎯', () => assertEq(scoreBand(300, 300), '🎯'));
test('99/100 → 🥇 (≥95%)', () => assertEq(scoreBand(99, 100), '🥇'));
test('90/100 → 🥈 (≥90%)', () => assertEq(scoreBand(90, 100), '🥈'));
test('85/100 → 🥉 (≥85%)', () => assertEq(scoreBand(85, 100), '🥉'));
test('80/100 → 🏆', () => assertEq(scoreBand(80, 100), '🏆'));
test('75/100 → ⚽', () => assertEq(scoreBand(75, 100), '⚽'));
test('70/100 → 🏟️', () => assertEq(scoreBand(70, 100), '🏟️'));
test('65/100 → 🏅', () => assertEq(scoreBand(65, 100), '🏅'));
test('60/100 → 🎽', () => assertEq(scoreBand(60, 100), '🎽'));
test('55/100 → 🏃', () => assertEq(scoreBand(55, 100), '🏃'));
test('50/100 → ⛳', () => assertEq(scoreBand(50, 100), '⛳'));
test('45/100 → 🏇', () => assertEq(scoreBand(45, 100), '🏇'));
test('40/100 → 🏎️', () => assertEq(scoreBand(40, 100), '🏎️'));
test('35/100 → 🥎', () => assertEq(scoreBand(35, 100), '🥎'));
test('30/100 → 🤔', () => assertEq(scoreBand(30, 100), '🤔'));
test('25/100 → 😬', () => assertEq(scoreBand(25, 100), '😬'));
test('20/100 → 🙈', () => assertEq(scoreBand(20, 100), '🙈'));
test('15/100 → 🤦', () => assertEq(scoreBand(15, 100), '🤦'));
test('10/100 → 💩', () => assertEq(scoreBand(10, 100), '💩'));
test('5/100 → 😭', () => assertEq(scoreBand(5, 100), '😭'));
test('1/100 → 🌚', () => assertEq(scoreBand(1, 100), '🌚'));
test('0/100 → 💀', () => assertEq(scoreBand(0, 100), '💀'));

suite('share.buildShareString');

const ROUND_MAX = [100, 100, 200, 300, 300];

test('all perfect shows 100 per round, day is 1-based', () => {
  const s = buildShareString(0, [100, 100, 200, 300, 300], ROUND_MAX);
  assertEq(s, 'https://stadia-game.netlify.app #1\n100🎯 100🎯 100🎯 100🎯 100🎯\nFinal score: 1000');
});

test('mixed — grid shows percentages, total shows raw, day is 1-based', () => {
  const s = buildShareString(42, [95, 90, 100, 150, 0], ROUND_MAX);
  assertEq(s, 'https://stadia-game.netlify.app #43\n95🥇 90🥈 50⛳ 50⛳ 0💀\nFinal score: 435');
});

test('total is the sum of raw round scores', () => {
  const s = buildShareString(1, [1, 2, 3, 4, 5], ROUND_MAX);
  assertEq(s.endsWith('Final score: 15'), true);
});
