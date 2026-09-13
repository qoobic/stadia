function isDev() {
  const h = location.hostname;
  return h === 'localhost' || h === '127.0.0.1' || h === '' || location.search.includes('?dev');
}

function send(name, params) {
  if (isDev()) { console.log('[analytics]', name, params); return; }
  if (typeof gtag !== 'function') return;
  gtag('event', name, params);
}

export function trackGameStarted(dayIndex, isReturningPlayer) {
  send('game_started', { day_index: dayIndex, is_returning_player: isReturningPlayer });
}

export function trackRoundCompleted({ dayIndex, roundIndex, band, targetVenue, guessedVenue, distanceKm, score, multiplier, countryBonus }) {
  send('round_completed', {
    day_index: dayIndex,
    round_index: roundIndex,
    band,
    target_venue_id: targetVenue.id,
    target_venue_name: targetVenue.name,
    target_venue_city: targetVenue.city,
    target_venue_country: targetVenue.country,
    venue_class: targetVenue.venueClass,
    guessed_venue_id: guessedVenue.id,
    guessed_venue_name: guessedVenue.name,
    guessed_venue_city: guessedVenue.city,
    guessed_venue_country: guessedVenue.country,
    distance_km: Math.round(distanceKm),
    score,
    multiplier,
    is_exact_match: targetVenue.id === guessedVenue.id,
    country_match: targetVenue.country === guessedVenue.country,
    country_bonus: countryBonus
  });
}

export function trackGameCompleted(dayIndex, totalScore, totalMax) {
  send('game_completed', {
    day_index: dayIndex,
    total_score: totalScore,
    score_pct: Math.round((totalScore / totalMax) * 100)
  });
}

export function trackShareCopied(dayIndex, totalScore) {
  send('share_copied', { day_index: dayIndex, total_score: totalScore });
}
