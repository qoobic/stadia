import { loadVenuesData, computeDayIndex, selectTodayVenues, todayDateString, getDayOffset, buildVenueIndex } from './venues.js';
import {
  initState, loadToday, saveToday, freshTodayState,
  recordRoundResult, markCompleted
} from './state.js';
import { initMap, showGuessState, showRevealState, showSummaryState, resetMap } from './map.js';
import { initPicker, resetPicker, focusPicker, getSelectedVenue } from './picker.js';
import { distanceKm, scoreForRound, countryBonus } from './score.js';
import { buildShareString, copyToClipboard } from './share.js';
import {
  renderRoundIndicator, renderGuessPrompt, renderRevealInfo, renderSummary,
  setPrimaryButton, hideFooter, showFooter, hidePicker, showPicker,
  initModal, initDevPanel, showCelebration
} from './ui.js';
import { trackGameStarted, trackRoundCompleted, trackGameCompleted, trackShareCopied } from './analytics.js';

const ROUND_MULTIPLIERS = [1, 1, 2, 3, 3];

document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    const btn = document.getElementById('primary-btn');
    if (btn && !btn.disabled) { btn.click(); e.preventDefault(); }
  }
});
const ROUND_MAXES = ROUND_MULTIPLIERS.map(m => 100 * m);

async function main() {
  initMap(document.getElementById('map'));
  initModal();

  let venuesData;
  try {
    venuesData = await loadVenuesData('data/live-venues.json');
  } catch (err) {
    showFatalError(`Couldn't load the venue data — ${err.message}`);
    return;
  }

  const venueIndex = buildVenueIndex(venuesData);
  initPicker(document.getElementById('picker'), venueIndex);

  const venueById = new Map(venueIndex.map(c => [c.id, c]));

  const now = new Date();
  const todayStr = todayDateString(now);
  const offset = getDayOffset();
  const dayIndex = computeDayIndex(now, venuesData.launchDate) + offset;
  const todayVenues = selectTodayVenues(dayIndex, venuesData);

  const isReturningPlayer = Object.keys(localStorage).some(k => k.startsWith('elev_day_'));

  initState(dayIndex);
  initDevPanel(dayIndex);

  let state = loadToday();
  if (!state || state.date !== todayStr || state.dayIndex !== dayIndex) {
    state = freshTodayState(todayStr, dayIndex);
    saveToday(state);
    trackGameStarted(dayIndex, isReturningPlayer);
  }

  rescoreInPlace(state, venueById);
  saveToday(state);

  if (state.completed) {
    showSummary(state, todayVenues, dayIndex, venueById);
    return;
  }

  while (true) {
    state = loadToday();
    if (!state || state.completed) break;
    const i = state.rounds.length;
    if (i >= 5) break;
    await playRound(i, todayVenues[i], dayIndex);
  }

  markCompleted();
  state = loadToday();
  trackGameCompleted(dayIndex, state.totalScore, ROUND_MAXES.reduce((a, b) => a + b, 0));
  showSummary(state, todayVenues, dayIndex, venueById);
  showCelebration(state.totalScore);
}

function rescoreInPlace(state, venueById) {
  let total = 0;
  for (const r of state.rounds) {
    const pick = venueById.get(r.pickId);
    const correct = venueById.get(r.targetId);
    if (!pick || !correct) { total += r.score; continue; }
    r.score = scoreForRound(pick, correct, r.multiplier);
    total += r.score;
  }
  state.totalScore = total;
}

async function playRound(roundIndex, targetVenue, dayIndex) {
  resetMap();
  resetPicker();
  showFooter();
  showPicker();
  renderRoundIndicator(roundIndex);
  renderGuessPrompt(roundIndex);
  showGuessState(targetVenue);
  setPrimaryButton('Submit guess', false);
  focusPicker();

  const enableSubmit = (e) => setPrimaryButton('Submit guess', !!e.detail.venue);
  document.addEventListener('stadia:picker-changed', enableSubmit);

  const btn = document.getElementById('primary-btn');
  const guess = await new Promise(resolve => {
    const onClick = () => {
      const picked = getSelectedVenue();
      if (!picked) return;
      btn.removeEventListener('click', onClick);
      resolve(picked);
    };
    btn.addEventListener('click', onClick);
  });
  document.removeEventListener('stadia:picker-changed', enableSubmit);

  const dist = distanceKm(guess, targetVenue);
  const multiplier = ROUND_MULTIPLIERS[roundIndex];
  const score = scoreForRound(guess, targetVenue, multiplier);
  const bonus = countryBonus(guess, targetVenue, multiplier);

  recordRoundResult({
    roundIndex,
    targetId: targetVenue.id,
    pickId: guess.id,
    distKm: dist,
    score,
    multiplier
  });

  trackRoundCompleted({
    dayIndex,
    roundIndex,
    band: `l${roundIndex + 1}`,
    targetVenue,
    guessedVenue: guess,
    distanceKm: dist,
    score,
    multiplier,
    countryBonus: bonus
  });

  hidePicker();
  showRevealState(targetVenue, guess);
  renderRevealInfo(targetVenue, dist, score, bonus);

  const isLast = roundIndex === 4;
  await autoAdvance(btn, isLast ? 'See your score' : 'Next round');
}

function autoAdvance(btn, label) {
  return new Promise(resolve => {
    let rem = 4;
    btn.disabled = false;
    btn.textContent = `${label} (${rem})`;
    const onClickEarly = () => { clearInterval(iv); resolve(); };
    btn.addEventListener('click', onClickEarly, { once: true });
    const iv = setInterval(() => {
      rem--;
      if (rem <= 0) {
        clearInterval(iv);
        btn.removeEventListener('click', onClickEarly);
        resolve();
      } else {
        btn.textContent = `${label} (${rem})`;
      }
    }, 1000);
  });
}

function showSummary(state, todayVenues, dayIndex, venueById) {
  const pairs = state.rounds
    .map((r, i) => ({ target: todayVenues[i], pick: venueById.get(r.pickId) }))
    .filter(p => p.target && p.pick);
  if (pairs.length) {
    showSummaryState(pairs);
  } else {
    resetMap();
  }
  renderRoundIndicator(5);
  hideFooter();

  const perRoundScores = state.rounds.map(r => r.score);
  const totalScore = state.totalScore;
  const totalMax = ROUND_MAXES.reduce((a, b) => a + b, 0);
  const shareString = buildShareString(dayIndex, perRoundScores, ROUND_MAXES);

  const bonuses = state.rounds.map((r, i) => {
    const pick = venueById.get(r.pickId);
    const correct = todayVenues[i];
    return (pick && correct) ? countryBonus(pick, correct, r.multiplier) : 0;
  });

  renderSummary(
    totalScore, totalMax, state.rounds, todayVenues, ROUND_MAXES,
    shareString, () => { trackShareCopied(dayIndex, totalScore); return copyToClipboard(shareString); },
    bonuses
  );
}

function showFatalError(msg) {
  const panel = document.getElementById('venue-panel');
  panel.innerHTML = '';
  const h = document.createElement('h2');
  h.textContent = 'Oh no';
  panel.appendChild(h);
  const p = document.createElement('p');
  p.textContent = msg;
  panel.appendChild(p);
  hideFooter();
}

main();
