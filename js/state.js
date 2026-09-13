const VERSION = 1;

let _todayIndex = null;
let memoryFallback = {};
let storageOk = true;

function tryStorage() {
  try {
    localStorage.setItem('__stadia_probe__', '1');
    localStorage.removeItem('__stadia_probe__');
    return true;
  } catch (_) {
    return false;
  }
}
storageOk = tryStorage();

function dayKey(dayIndex) { return `stadia_day_${dayIndex}`; }
function todayKey() {
  if (_todayIndex === null) throw new Error('initState not called');
  return dayKey(_todayIndex);
}

function readKey(key) {
  if (!storageOk) return memoryFallback[key] ?? null;
  const raw = localStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}

function writeKey(key, value) {
  if (!storageOk) { memoryFallback[key] = value; return; }
  try { localStorage.setItem(key, JSON.stringify(value)); }
  catch (_) { storageOk = false; memoryFallback[key] = value; }
}

function removeKey(key) {
  if (!storageOk) { delete memoryFallback[key]; return; }
  localStorage.removeItem(key);
}

export function initState(dayIndex) {
  _todayIndex = dayIndex;
}

export function freshTodayState(dateStr, dayIndex) {
  return {
    version: VERSION,
    date: dateStr,
    dayIndex,
    rounds: [],
    completed: false,
    totalScore: 0
  };
}

export function loadToday() { return readKey(todayKey()); }
export function saveToday(state) { writeKey(todayKey(), state); }

export function recordRoundResult(result) {
  const s = loadToday();
  if (!s) throw new Error('recordRoundResult called before saveToday');
  if (s.completed) return;
  const idx = result.roundIndex ?? s.rounds.length;
  if (s.rounds.some(r => r.roundIndex === idx)) return;
  if (s.rounds.length >= 5) return;
  s.rounds.push({ ...result, roundIndex: idx });
  s.totalScore = s.rounds.reduce((sum, r) => sum + r.score, 0);
  saveToday(s);
}

export function markCompleted() {
  const s = loadToday();
  if (!s) throw new Error('markCompleted called before saveToday');
  s.completed = true;
  saveToday(s);
}

export function loadDay(dayIndex) { return readKey(dayKey(dayIndex)); }
export function clearDay(dayIndex) { removeKey(dayKey(dayIndex)); }


export function _resetForTesting() {
  _todayIndex = null;
  memoryFallback = {};
  storageOk = tryStorage();
}
