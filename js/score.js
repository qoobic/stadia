const EARTH_RADIUS_KM = 6371.0088;
const KM_TO_MILES = 0.621371;

export function distanceKm(a, b) {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

const COUNTRY_BONUS = 10;
const WRONG_CITY_CAP = 90;

function distanceScore(pick, correct) {
  const distMiles = distanceKm(pick, correct) * KM_TO_MILES;
  const n = Math.max(1, Math.ceil((-39 + Math.sqrt(1521 + 8 * distMiles)) / 2));
  return Math.max(0, 101 - n);
}

export function scoreForRound(pick, correct, multiplier) {
  const ds = distanceScore(pick, correct);
  if (pick.id === correct.id) return ds * multiplier;
  const bonus = pick.country === correct.country ? COUNTRY_BONUS : 0;
  return Math.min(ds + bonus, WRONG_CITY_CAP) * multiplier;
}

export function countryBonus(pick, correct, multiplier) {
  if (pick.id === correct.id || pick.country !== correct.country) return 0;
  const ds = distanceScore(pick, correct);
  const withBonus = Math.min(ds + COUNTRY_BONUS, WRONG_CITY_CAP);
  const without = Math.min(ds, WRONG_CITY_CAP);
  return (withBonus - without) * multiplier;
}
