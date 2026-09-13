import { clearDay } from './state.js';
import { setDayOffset, getDayOffset } from './venues.js';

export function renderRoundIndicator(currentRoundIndex) {
  const el = document.getElementById('round-indicator');
  el.innerHTML = '';
  for (let i = 0; i < 5; i++) {
    const dot = document.createElement('span');
    dot.className = 'dot' + (i === currentRoundIndex ? ' active' : (i < currentRoundIndex ? ' done' : ''));
    el.appendChild(dot);
  }
}

export function renderGuessPrompt(roundIndex) {
  const panel = document.getElementById('venue-panel');
  panel.innerHTML = '';
  const p = document.createElement('div');
  p.className = 'clue-prompt';
  p.textContent = `Round ${roundIndex + 1} of 5 — which venue is this?`;
  panel.appendChild(p);
}

export function renderRevealInfo(targetVenue, distanceKm, score, bonus = 0) {
  const panel = document.getElementById('venue-panel');
  panel.innerHTML = '';

  const name = document.createElement('div');
  name.className = 'reveal-name';
  name.textContent = targetVenue.name;
  panel.appendChild(name);

  const loc = document.createElement('div');
  loc.className = 'reveal-location';
  loc.textContent = `${targetVenue.city}, ${targetVenue.country}`;
  panel.appendChild(loc);

  const distEl = document.createElement('div');
  distEl.className = 'reveal-distance';
  distEl.textContent = distanceKm === 0
    ? 'Exact!'
    : `${Math.round(distanceKm).toLocaleString()} km away`;
  panel.appendChild(distEl);

  const scoreEl = document.createElement('div');
  scoreEl.className = 'reveal-score';
  scoreEl.textContent = `+${score} points`;
  panel.appendChild(scoreEl);

  if (bonus > 0) {
    const bonusEl = document.createElement('div');
    bonusEl.className = 'reveal-bonus';
    bonusEl.textContent = `+${bonus} right-country bonus`;
    panel.appendChild(bonusEl);
  }
}

export function renderSummary(totalScore, totalMax, perRoundResults, todayVenues, perRoundMaxes, shareString, onCopyShare, bonuses = []) {
  const panel = document.getElementById('venue-panel');
  panel.innerHTML = '';

  const title = document.createElement('h2');
  title.textContent = "Today's score";
  title.className = 'summary-title';
  panel.appendChild(title);

  const total = document.createElement('div');
  total.className = 'summary-total';
  total.textContent = `${totalScore} / ${totalMax}`;
  panel.appendChild(total);

  const list = document.createElement('ol');
  list.className = 'summary-list';
  perRoundResults.forEach((r, i) => {
    const li = document.createElement('li');
    const place = document.createElement('span');
    place.className = 'summary-place';
    place.textContent = `${todayVenues[i].name}, ${todayVenues[i].city}`;
    const right = document.createElement('span');
    right.className = 'summary-right';

    const bonus = bonuses[i] || 0;
    if (bonus > 0) {
      const bonusSpan = document.createElement('span');
      bonusSpan.className = 'summary-bonus';
      bonusSpan.textContent = `+${bonus}`;
      right.appendChild(bonusSpan);
    }

    const scoreSpan = document.createElement('span');
    scoreSpan.className = 'summary-score';
    scoreSpan.textContent = `${r.score} / ${perRoundMaxes[i]}`;
    right.appendChild(scoreSpan);

    li.appendChild(place);
    li.appendChild(right);
    list.appendChild(li);
  });
  panel.appendChild(list);

  const shareBtn = document.createElement('button');
  shareBtn.className = 'share-btn';
  shareBtn.textContent = 'Copy result';
  shareBtn.addEventListener('click', async () => {
    panel.querySelector('.share-fallback')?.remove();
    const ok = await onCopyShare();
    shareBtn.textContent = ok ? 'Copied!' : 'Copy failed — long-press to copy:';
    if (!ok) {
      const pre = document.createElement('pre');
      pre.className = 'share-fallback';
      pre.textContent = shareString;
      panel.appendChild(pre);
    }
    setTimeout(() => { shareBtn.textContent = 'Copy result'; }, 2000);
  });
  panel.appendChild(shareBtn);

  const crossSell = document.createElement('div');
  crossSell.className = 'cross-sell';
  crossSell.innerHTML = 'Enjoying Stadia? Try <a href="https://elevation-game.netlify.app" target="_blank" rel="noopener">Elevation</a>';
  panel.appendChild(crossSell);
}

export function setPrimaryButton(label, enabled) {
  const btn = document.getElementById('primary-btn');
  btn.textContent = label;
  btn.disabled = !enabled;
}

export function hideFooter() {
  document.getElementById('footer').style.display = 'none';
}

export function showFooter() {
  document.getElementById('footer').style.display = '';
}

export function hidePicker() {
  document.getElementById('picker').style.display = 'none';
}

export function showPicker() {
  document.getElementById('picker').style.display = '';
}

export function initModal() {
  const modal = document.getElementById('venue-modal');
  const header = document.getElementById('modal-header');

  const toggle = document.createElement('button');
  toggle.id = 'modal-toggle';
  toggle.textContent = '−';
  toggle.title = 'Collapse';
  header.appendChild(toggle);

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    const collapsed = modal.classList.toggle('collapsed');
    toggle.textContent = collapsed ? '+' : '−';
    toggle.title = collapsed ? 'Expand' : 'Collapse';
  });

  let dragging = false;
  let startX, startY, startLeft, startTop;

  header.addEventListener('mousedown', (e) => {
    if (e.target === toggle) return;
    dragging = true;
    const rect = modal.getBoundingClientRect();
    startX = e.clientX; startY = e.clientY;
    startLeft = rect.left; startTop = rect.top;
    modal.style.right = 'auto';
    modal.style.left = startLeft + 'px';
    modal.style.top = startTop + 'px';
    header.style.cursor = 'grabbing';
    e.preventDefault();
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const newLeft = Math.max(0, Math.min(window.innerWidth - modal.offsetWidth, startLeft + e.clientX - startX));
    const newTop  = Math.max(0, Math.min(window.innerHeight - modal.offsetHeight, startTop + e.clientY - startY));
    modal.style.left = newLeft + 'px';
    modal.style.top  = newTop + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    header.style.cursor = '';
  });
}

export function initDevPanel(dayIndex) {
  const panel = document.getElementById('dev-panel');
  if (!panel) return;

  const isDev = ['localhost', '127.0.0.1', ''].includes(location.hostname) || location.search.includes('dev');
  if (!isDev) { panel.remove(); return; }

  panel.innerHTML = '';

  const label = document.createElement('span');
  label.textContent = `Day ${dayIndex + 1}`;

  const prev = document.createElement('button');
  prev.textContent = '−';
  prev.title = 'Previous day';
  prev.addEventListener('click', () => { setDayOffset(getDayOffset() - 1); location.reload(); });

  const input = document.createElement('input');
  input.type = 'number';
  input.value = dayIndex + 1;
  input.title = 'Jump to day';
  input.addEventListener('change', () => {
    const target = parseInt(input.value, 10) - 1;
    if (Number.isFinite(target)) {
      setDayOffset(target - (dayIndex - getDayOffset()));
      location.reload();
    }
  });

  const next = document.createElement('button');
  next.textContent = '+';
  next.title = 'Next day';
  next.addEventListener('click', () => { setDayOffset(getDayOffset() + 1); location.reload(); });

  const reset = document.createElement('button');
  reset.textContent = '↺';
  reset.title = 'Reset to today';
  reset.addEventListener('click', () => { setDayOffset(0); location.reload(); });

  const clearBtn = document.createElement('button');
  clearBtn.textContent = '✕';
  clearBtn.title = 'Clear today and reattempt';
  clearBtn.addEventListener('click', () => { clearDay(dayIndex); location.reload(); });

  const testScoreInput = document.createElement('input');
  testScoreInput.type = 'number';
  testScoreInput.value = 1000;
  testScoreInput.title = 'Score to test celebration';

  const testCelebBtn = document.createElement('button');
  testCelebBtn.textContent = '🎉';
  testCelebBtn.title = 'Test celebration at this score';
  testCelebBtn.addEventListener('click', () => showCelebration(parseInt(testScoreInput.value, 10) || 1000));

  panel.append(label, prev, input, next, reset, clearBtn, testScoreInput, testCelebBtn);
}

// One emoji per venue class, plus a few of the sports those venues host.
const CELEBRATION_EMOJI = ['⚽', '🏈', '🏉', '🎾', '🐎', '🏎️', '⛳', '🏀', '🏏'];
// Emoji need a larger scalar than default confetti to stay legible, and fewer
// particles to stay cheap — each one is a rendered glyph, not a coloured rect.
const PARTICLE_SCALAR = 3.2;
const PARTICLE_COUNT = 34;

let cachedShapes = null;

function celebrationShapes() {
  if (cachedShapes) return cachedShapes;
  // Older canvas-confetti builds have no shapeFromText; fall back to plain
  // confetti rather than failing. (confetti itself must exist — the caller
  // uses confetti.create regardless.)
  if (typeof confetti.shapeFromText !== 'function') return undefined;
  try {
    cachedShapes = CELEBRATION_EMOJI.map(text => confetti.shapeFromText({ text, scalar: PARTICLE_SCALAR }));
  } catch (_) {
    cachedShapes = null;
    return undefined;
  }
  return cachedShapes;
}

const CELEBRATION_THRESHOLD = 950;
const CELEBRATION_PHRASES = [
  'YOU KNOW EVERY BLADE OF GRASS!',
  'ARE YOU A GROUNDSKEEPER IN DISGUISE!?',
  'YOU COULD FIND THE CENTRE CIRCLE BLINDFOLD!',
  'DO YOU DREAM IN FLOODLIGHTS!?',
  'THAT IS A STADIUM-SHAPED BRAIN!',
  'YOU MUST HAVE AN AWFUL LOT OF SEASON TICKETS!',
  'THE FOURTH OFFICIAL IS ADDING SEVEN MINUTES OF APPLAUSE!',
  'SUSPICIOUSLY GOOD. HAVE YOU PLAYED AT ALL OF THEM!?',
  'BACK OF THE NET, FROM ORBIT!',
  'YOU SCOUT PITCHES THE WAY OTHERS SCOUT PLAYERS!',
  'ARE YOU THE BLIMP CAMERA OPERATOR!?',
];

export function showCelebration(score) {
  if (score < CELEBRATION_THRESHOLD) return;
  const phrase = CELEBRATION_PHRASES[score % CELEBRATION_PHRASES.length];

  const existing = document.getElementById('celebration-overlay');
  if (existing) {
    clearInterval(existing._fireworksInterval);
    existing._confettiReset?.();
    existing.remove();
  }

  const overlay = document.createElement('div');
  overlay.id = 'celebration-overlay';

  const canvas = document.createElement('canvas');
  canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;';
  overlay.appendChild(canvas);

  const phraseEl = document.createElement('div');
  phraseEl.className = 'celebration-phrase';
  phraseEl.textContent = phrase;
  overlay.appendChild(phraseEl);

  document.getElementById('app').appendChild(overlay);

  const myConfetti = confetti.create(canvas, { resize: true });
  overlay._confettiReset = () => myConfetti.reset();
  const shapes = celebrationShapes();
  const fire = () => {
    myConfetti({ angle: 60, spread: 60, origin: { x: 0 }, particleCount: PARTICLE_COUNT, shapes, scalar: PARTICLE_SCALAR });
    myConfetti({ angle: 120, spread: 60, origin: { x: 1 }, particleCount: PARTICLE_COUNT, shapes, scalar: PARTICLE_SCALAR });
  };
  fire();
  overlay._fireworksInterval = setInterval(fire, 2500);
}
