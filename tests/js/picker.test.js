import { suite, test, assertTrue, assertEq } from './runner.js';
import { initPicker, getSelectedVenue } from '../../js/picker.js';
import { buildVenueIndex } from '../../js/venues.js';

suite('picker');

function setup() {
  const venuesData = {
    l1: [
      { id: 'eden-gardens', name: 'Eden Gardens', city: 'Kolkata', country: 'India', aliases: [] },
      { id: 'wankhede', name: 'Wankhede Stadium', city: 'Mumbai', country: 'India', aliases: [] }
    ],
    l2: [], l3: [], l4: [], l5: []
  };
  const index = buildVenueIndex(venuesData);
  const container = document.createElement('div');
  document.body.appendChild(container);
  initPicker(container, index);
  const input = container.querySelector('input');
  input.value = 'India';
  input.dispatchEvent(new Event('input'));
  const list = document.querySelector('ul.suggestions');
  return { input, list };
}

function makeTouch(el, y) {
  return new Touch({ identifier: 1, target: el, clientX: 0, clientY: y });
}

function fireTouch(el, type, y) {
  const t = makeTouch(el, y);
  const ev = new TouchEvent(type, {
    bubbles: true, cancelable: true, touches: [t], changedTouches: [t]
  });
  el.dispatchEvent(ev);
  return ev;
}

test('touchstart on a suggestion does not cancel native scroll', () => {
  const { list } = setup();
  const li = list.querySelectorAll('li')[0];
  const ev = fireTouch(li, 'touchstart', 100);
  assertTrue(!ev.defaultPrevented, 'touchstart must not preventDefault, or the list cannot scroll on touch');
});

test('a tap (touchstart + touchend, no movement) selects the venue', () => {
  const { list } = setup();
  const li = list.querySelectorAll('li')[1];
  fireTouch(li, 'touchstart', 100);
  fireTouch(li, 'touchend', 100);
  assertTrue(getSelectedVenue() != null, 'a clean tap should select a venue');
  assertEq(getSelectedVenue().name, 'Wankhede Stadium');
});

test('a scroll gesture (touchmove past threshold) does not select a venue', () => {
  const { list } = setup();
  const li = list.querySelectorAll('li')[0];
  fireTouch(li, 'touchstart', 200);
  fireTouch(li, 'touchmove', 140);
  fireTouch(li, 'touchend', 140);
  assertTrue(getSelectedVenue() == null, 'dragging to scroll must not select a venue');
});
