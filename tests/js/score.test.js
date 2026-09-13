import { suite, test, assertApprox, assertEq } from './runner.js';
import { distanceKm, scoreForRound } from '../../js/score.js';

suite('score.distanceKm');

test('zero distance for identical points', () => {
  assertApprox(distanceKm({ lat: 51.5, lng: -0.1 }, { lat: 51.5, lng: -0.1 }), 0, 0.01);
});

test('London to Paris ≈ 344 km', () => {
  const d = distanceKm({ lat: 51.5074, lng: -0.1278 }, { lat: 48.8566, lng: 2.3522 });
  assertApprox(d, 344, 5);
});

test('Sydney to LA ≈ 12073 km', () => {
  const d = distanceKm({ lat: -33.8688, lng: 151.2093 }, { lat: 34.0522, lng: -118.2437 });
  assertApprox(d, 12073, 30);
});

test('antipodal points ≈ 20015 km', () => {
  const d = distanceKm({ lat: 0, lng: 0 }, { lat: 0, lng: 180 });
  assertApprox(d, 20015, 5);
});

suite('score.scoreForRound');

const paris = { id: 'paris', country: 'France', lat: 48.8566, lng: 2.3522 };
const lyon  = { id: 'lyon',  country: 'France', lat: 45.7640, lng: 4.8357 };
const ldn   = { id: 'london', country: 'UK', lat: 51.5074, lng: -0.1278 };

test('exact same city → full marks (100 * multiplier)', () => {
  assertEq(scoreForRound(paris, paris, 1), 100);
  assertEq(scoreForRound(paris, paris, 3), 300);
});

test('wrong city, right country (Lyon→Paris ~391 km) capped at 90 with bonus', () => {
  assertEq(scoreForRound(lyon, paris, 1), 90);
});

test('wrong city, wrong country (London→Paris ~344 km) at multiplier 2 → 180', () => {
  assertEq(scoreForRound(ldn, paris, 2), 180);
});

test('huge distance, wrong country (Sydney→LA at multiplier 1) → 0', () => {
  const sydney = { id: 's', country: 'Australia', lat: -33.8688, lng: 151.2093 };
  const la     = { id: 'la', country: 'USA', lat: 34.0522, lng: -118.2437 };
  assertEq(scoreForRound(sydney, la, 1), 0);
});

test('far miss but right country keeps the +10 bonus (Vladivostok→Moscow) → 39', () => {
  const vlad   = { id: 'v', country: 'Russia', lat: 43.1155, lng: 131.8855 };
  const moscow = { id: 'm', country: 'Russia', lat: 55.7558, lng: 37.6173 };
  assertEq(scoreForRound(vlad, moscow, 1), 39);
});
