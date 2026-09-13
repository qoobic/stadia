import { searchVenues, venueLabel } from './venues.js';

let container = null;
let input = null;
let list = null;
let venueIndex = null;
let suggestions = [];
let activeIndex = -1;
let selectedVenue = null;
let touchStartY = 0;
let touchMoved = false;
const TOUCH_MOVE_THRESHOLD = 8;

export function initPicker(containerEl, builtIndex) {
  container = containerEl;
  venueIndex = builtIndex;
  suggestions = [];
  activeIndex = -1;
  selectedVenue = null;

  container.innerHTML = '';
  input = document.createElement('input');
  input.type = 'text';
  input.autocomplete = 'off';
  input.spellcheck = false;
  input.placeholder = 'Type a venue…';

  if (list && list.parentNode) list.parentNode.removeChild(list);
  list = document.createElement('ul');
  list.className = 'suggestions';
  list.classList.add('hidden');
  document.body.appendChild(list);

  container.append(input);

  input.addEventListener('input', onInput);
  input.addEventListener('keydown', onKeyDown);

  document.removeEventListener('pointerdown', onDocumentPointerDown, true);
  document.addEventListener('pointerdown', onDocumentPointerDown, true);
}

function onDocumentPointerDown(e) {
  if (!list || list.classList.contains('hidden')) return;
  if (input.contains(e.target) || list.contains(e.target)) return;
  closeList();
}

export function resetPicker() {
  if (!input) return;
  input.value = '';
  input.classList.remove('selected');
  suggestions = [];
  activeIndex = -1;
  selectedVenue = null;
  renderSuggestions();
  notifyChanged();
}

export function focusPicker() {
  input?.focus();
}

export function getSelectedVenue() {
  return selectedVenue;
}

function onInput() {
  selectedVenue = null;
  input.classList.remove('selected');
  suggestions = searchVenues(venueIndex, input.value);
  activeIndex = suggestions.length ? 0 : -1;
  renderSuggestions();
  notifyChanged();
}

function onKeyDown(e) {
  if (e.key === 'ArrowDown') {
    if (!suggestions.length) return;
    activeIndex = (activeIndex + 1) % suggestions.length;
    renderSuggestions();
    e.preventDefault();
  } else if (e.key === 'ArrowUp') {
    if (!suggestions.length) return;
    activeIndex = (activeIndex - 1 + suggestions.length) % suggestions.length;
    renderSuggestions();
    e.preventDefault();
  } else if (e.key === 'Enter') {
    if (activeIndex >= 0 && suggestions[activeIndex]) {
      pickVenue(suggestions[activeIndex]);
      e.preventDefault();
    }
  } else if (e.key === 'Escape') {
    if (input.value !== '') {
      input.value = '';
      onInput();
    } else {
      closeList();
    }
  }
}

function pickVenue(venue) {
  selectedVenue = venue;
  input.value = venueLabel(venue);
  input.classList.add('selected');
  suggestions = [];
  activeIndex = -1;
  renderSuggestions();
  notifyChanged();
}

function renderSuggestions() {
  list.innerHTML = '';
  if (suggestions.length === 0) {
    list.classList.add('hidden');
    return;
  }

  const rect = input.getBoundingClientRect();
  const available = window.innerHeight - rect.bottom - 8;
  list.style.top = (rect.bottom + 2) + 'px';
  list.style.left = rect.left + 'px';
  list.style.width = rect.width + 'px';
  list.style.maxHeight = Math.min(available, 14 * 16) + 'px';

  list.classList.remove('hidden');
  suggestions.forEach((c, i) => {
    const li = document.createElement('li');
    li.textContent = venueLabel(c);
    if (i === activeIndex) li.classList.add('active');
    li.addEventListener('mousedown', (e) => { e.preventDefault(); pickVenue(c); });
    li.addEventListener('touchstart', (e) => {
      touchMoved = false;
      touchStartY = e.touches[0] ? e.touches[0].clientY : 0;
    }, { passive: true });
    li.addEventListener('touchmove', (e) => {
      const y = e.touches[0] ? e.touches[0].clientY : touchStartY;
      if (Math.abs(y - touchStartY) > TOUCH_MOVE_THRESHOLD) touchMoved = true;
    }, { passive: true });
    li.addEventListener('touchend', (e) => {
      if (touchMoved) return;
      e.preventDefault();
      pickVenue(c);
    }, { passive: false });
    list.appendChild(li);
  });
}

function closeList() {
  suggestions = [];
  activeIndex = -1;
  renderSuggestions();
}

function notifyChanged() {
  document.dispatchEvent(new CustomEvent('stadia:picker-changed', { detail: { venue: selectedVenue } }));
}
