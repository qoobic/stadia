export function scoreBand(score, max) {
  if (score <= 0 || max <= 0) return '💀';
  if (score === max) return '🎯';
  const pct = (score / max) * 100;
  if (pct >= 95) return '🥇';
  if (pct >= 90) return '🥈';
  if (pct >= 85) return '🥉';
  if (pct >= 80) return '🏆';
  if (pct >= 75) return '⚽';
  if (pct >= 70) return '🏟️';
  if (pct >= 65) return '🏅';
  if (pct >= 60) return '🎽';
  if (pct >= 55) return '🏃';
  if (pct >= 50) return '⛳';
  if (pct >= 45) return '🏇';
  if (pct >= 40) return '🏎️';
  if (pct >= 35) return '🥎';
  if (pct >= 30) return '🤔';
  if (pct >= 25) return '😬';
  if (pct >= 20) return '🙈';
  if (pct >= 15) return '🤦';
  if (pct >= 10) return '💩';
  if (pct >= 5)  return '😭';
  return '🌚';
}

export function buildShareString(dayIndex, perRoundScores, perRoundMaxes) {
  const grid = perRoundScores.map((s, i) => {
    const pct = Math.round(s / perRoundMaxes[i] * 100);
    return `${pct}${scoreBand(s, perRoundMaxes[i])}`;
  }).join(' ');
  const total = perRoundScores.reduce((a, b) => a + b, 0);
  return `https://stadia-game.netlify.app #${dayIndex + 1}\n${grid}\nFinal score: ${total}`;
}

export async function copyToClipboard(text) {
  if (navigator.share) {
    try {
      await navigator.share({ text });
      return true;
    } catch (e) {
      if (e.name !== 'AbortError') return false;
    }
  }
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {}
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.top = '-1000px';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch (_) {}
  finally {
    document.body.removeChild(ta);
  }
  return ok;
}
