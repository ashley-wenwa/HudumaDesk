/* Leaflet map: "pick" mode lets a citizen drop a pin, "view" mode shows a saved one. */
(function () {
  var el = document.getElementById("map");
  if (!el || !window.L) { if (el) el.hidden = true; return; }

  var pick = el.dataset.mode === "pick";
  var lat = parseFloat(el.dataset.lat), lng = parseFloat(el.dataset.lng);
  var hasPin = !isNaN(lat) && !isNaN(lng);

  var map = L.map(el).setView(hasPin ? [lat, lng] : [-1.2864, 36.8172], hasPin ? 16 : 11);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);
  var marker = hasPin ? L.marker([lat, lng]).addTo(map) : null;
  if (!pick) return;

  function setPin(la, ln) {
    document.getElementById("latitude").value = la.toFixed(6);
    document.getElementById("longitude").value = ln.toFixed(6);
    if (marker) { marker.setLatLng([la, ln]); } else { marker = L.marker([la, ln]).addTo(map); }
  }
  map.on("click", function (e) { setPin(e.latlng.lat, e.latlng.lng); });

  document.getElementById("locate").addEventListener("click", function () {
    if (!navigator.geolocation) { return; }
    navigator.geolocation.getCurrentPosition(function (pos) {
      setPin(pos.coords.latitude, pos.coords.longitude);
      map.setView([pos.coords.latitude, pos.coords.longitude], 16);
    });
  });
})();
