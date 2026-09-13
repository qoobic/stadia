import { suite, test, assertEq } from './runner.js';

suite('smoke');

test('1 + 1 === 2', () => {
  assertEq(1 + 1, 2);
});
