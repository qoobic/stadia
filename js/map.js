const TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
const TILE_ATTRIBUTION = 'Imagery © Esri';
const ZOOM_OUT_ALLOWANCE = 3;

let map = null;
let truthMarker = null;
let pickMarker = null;
let line = null;
let truthLabel = null;
let summaryLayers = [];

export function initMap(container) {
  map = L.map(container, {
    zoomControl: false,
    attributionControl: true,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    touchZoom: false,
    boxZoom: false,
    keyboard: false,
    worldCopyJump: false,
    maxBoundsViscosity: 1.0,
    bounceAtZoomLimits: false
  }).setView([20, 0], 3);
  L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION }).addTo(map);
}

export function showGuessState(targetVenue) {
  clearRevealLayers();
  map.setMaxBounds(null);

  const defaultZoom = targetVenue.zoom;
  const minZoom = defaultZoom - ZOOM_OUT_ALLOWANCE;
  map.setMinZoom(minZoom);
  map.setMaxZoom(18);
  map.setView([targetVenue.lat, targetVenue.lng], defaultZoom, { animate: false });

  // The guess view stays locked on the venue. Panning is off, and every zoom is
  // anchored to the centre — otherwise zooming toward the cursor would let you
  // pan by repeatedly zooming in and out.
  lockPanning();
  setZoomAnchor('center');
  map.scrollWheelZoom.enable();
  map.doubleClickZoom.enable();
  map.touchZoom.enable();
}

function lockPanning() {
  map.dragging.disable();
  map.keyboard.disable();
}

function freePanning() {
  map.dragging.enable();
  map.keyboard.enable();
}

// Leaflet reads these options at zoom time, so they must be set before enabling
// the handlers. 'center' keeps the view anchored; true zooms toward the pointer.
function setZoomAnchor(mode) {
  map.options.scrollWheelZoom = mode;
  map.options.doubleClickZoom = mode;
  map.options.touchZoom = mode;
}

function nearestCopyLng(targetLng, referenceLng) {
  const diff = targetLng - referenceLng;
  return targetLng - Math.round(diff / 360) * 360;
}

export function showRevealState(targetVenue, pickVenue) {
  clearRevealLayers();
  map.setMaxBounds(null);
  map.setMinZoom(1);
  map.setMaxZoom(18);
  setZoomAnchor(true);
  freePanning();

  const refLng = targetVenue.lng;
  const pickLng = nearestCopyLng(pickVenue.lng, refLng);

  truthMarker = L.circleMarker([targetVenue.lat, targetVenue.lng], {
    radius: 9, color: '#22c55e', weight: 3, fillColor: '#22c55e', fillOpacity: 0.6
  }).addTo(map);

  pickMarker = L.circleMarker([pickVenue.lat, pickLng], {
    radius: 9, color: '#facc15', weight: 3, fillColor: '#facc15', fillOpacity: 0.6
  }).addTo(map);

  line = L.polyline(
    [[targetVenue.lat, targetVenue.lng], [pickVenue.lat, pickLng]],
    { color: '#facc15', weight: 2, dashArray: '6 6' }
  ).addTo(map);

  truthLabel = L.popup({ closeButton: false, autoClose: false, closeOnClick: false, className: 'stadia-truth-label' })
    .setLatLng([targetVenue.lat, targetVenue.lng])
    .setContent(`<strong>${escapeHtml(targetVenue.name)}</strong><br>${escapeHtml(targetVenue.city)}, ${escapeHtml(targetVenue.country)}`)
    .openOn(map);

  const bounds = L.latLngBounds([targetVenue.lat, targetVenue.lng], [pickVenue.lat, pickLng]);
  if (bounds.getNorthEast().equals(bounds.getSouthWest())) {
    map.setView([targetVenue.lat, targetVenue.lng], Math.min(targetVenue.zoom, 12), { animate: true });
  } else {
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 6, animate: true });
  }
}

export function showSummaryState(pairs) {
  clearRevealLayers();
  map.setMaxBounds(null);
  map.setMinZoom(1);

  const maxZoom = Math.max(...pairs.flatMap(p => [p.target.zoom, p.pick.zoom]));
  map.setMaxZoom(maxZoom);

  const answerIds = new Set(pairs.map(p => p.target.id));
  const seen = new Set();
  const points = [];

  for (const { target, pick } of pairs) {
    const pickLng = nearestCopyLng(pick.lng, target.lng);
    const l = L.polyline(
      [[target.lat, target.lng], [pick.lat, pickLng]],
      { color: '#facc15', weight: 2, dashArray: '6 6' }
    ).addTo(map);
    summaryLayers.push(l);
    points.push([target.lat, target.lng], [pick.lat, pickLng]);
  }

  for (const { target, pick } of pairs) {
    const pickLng = nearestCopyLng(pick.lng, target.lng);
    const radius = answerIds.has(pick.id) ? 14 : 9;
    const p = L.circleMarker([pick.lat, pickLng], {
      radius, color: '#facc15', weight: 3, fillColor: '#facc15', fillOpacity: 0.6
    }).addTo(map);
    summaryLayers.push(p);
  }

  for (const { target } of pairs) {
    const t = L.circleMarker([target.lat, target.lng], {
      radius: 9, color: '#22c55e', weight: 3, fillColor: '#22c55e', fillOpacity: 0.6
    }).addTo(map);
    summaryLayers.push(t);
  }

  for (const { target } of pairs) {
    addSummaryLabel(seen, target, target.lat, target.lng);
  }
  for (const { target, pick } of pairs) {
    addSummaryLabel(seen, pick, pick.lat, nearestCopyLng(pick.lng, target.lng));
  }

  if (points.length) {
    map.fitBounds(L.latLngBounds(points), { padding: [60, 60], maxZoom, animate: false });
  }

  setZoomAnchor(true);
  freePanning();
  map.scrollWheelZoom.enable();
  map.doubleClickZoom.enable();
  map.touchZoom.enable();
}

function addSummaryLabel(seen, venue, lat, lng) {
  if (seen.has(venue.id)) return;
  seen.add(venue.id);
  const popup = L.popup({ closeButton: false, autoClose: false, closeOnClick: false, className: 'stadia-truth-label' })
    .setLatLng([lat, lng])
    .setContent(`<strong>${escapeHtml(venue.name)}</strong><br>${escapeHtml(venue.city)}, ${escapeHtml(venue.country)}`);
  popup.addTo(map);
  summaryLayers.push(popup);
}

export function resetMap() {
  clearRevealLayers();
  map.setMaxBounds(null);
  map.setMinZoom(1);
  map.setMaxZoom(18);
  map.setView([20, 0], 3, { animate: false });
}

function clearRevealLayers() {
  if (truthMarker) { map.removeLayer(truthMarker); truthMarker = null; }
  if (pickMarker)  { map.removeLayer(pickMarker);  pickMarker  = null; }
  if (line)        { map.removeLayer(line);        line        = null; }
  if (truthLabel)  { map.closePopup(truthLabel);   truthLabel  = null; }
  if (summaryLayers.length) {
    summaryLayers.forEach(layer => map.removeLayer(layer));
    summaryLayers = [];
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}
