// docs/js/main_mapbox.js
(() => {
  // Data path (same behavior as before)
  const DATA_URL = new URL("./data/tours.geojson", document.baseURI).href;

  // Mapbox config
  const MAP_STYLE = "mapbox://styles/mapbox/outdoors-v12";

  // Optional 3D terrain (you can disable by setting to false)
  const ENABLE_3D_TERRAIN = true;
  const DEM_SOURCE_URL = "mapbox://mapbox.terrain-rgb";
  const TERRAIN_EXAGGERATION = 1.3;

  let map;
  let allFeatures = [];

  function $(id) {
    return document.getElementById(id);
  }

  function norm(s) {
    return (s ?? "").toString().trim().toLowerCase();
  }

  function openTour(p) {
    const url = p.page || (p.slug ? `./tours/${p.slug}.html` : null);
    if (!url) return;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  // Direction -> color (supports typo 'direcrtion' too)
  function trackColorFromProps(p) {
    const d = norm(p?.direction || p?.direcrtion || "");
    if (d === "up" || d === "ascent") return "#1f6feb";      // blue
    if (d === "down" || d === "descent") return "#b64a4a";   // calm red
    if (d === "traverse" || d === "cross") return "#b000b5"; // magenta
    return "#1f6feb";
  }

  function passesFilters(p) {
    const q = norm($("q")?.value);
    const prov = norm($("province")?.value);
    const reg = norm($("region")?.value);

    const hay =
      `${norm(p.title)} ${norm(p.region)} ${norm(p.province)} ${norm(p.subtitle)} ${norm(p.country)}`;

    if (q && !hay.includes(q)) return false;
    if (prov && norm(p.province) !== prov) return false;
    if (reg && norm(p.region) !== reg) return false;
    return true;
  }

  function uniqSorted(arr) {
    return Array.from(new Set(arr.filter(Boolean))).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: "base" })
    );
  }

  function populateSelect(id, values, allLabel) {
    const el = $(id);
    if (!el) return;

    const current = el.value;

    el.innerHTML = "";
    const optAll = document.createElement("option");
    optAll.value = "";
    optAll.textContent = allLabel;
    el.appendChild(optAll);

    for (const v of values) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      el.appendChild(opt);
    }

    if (values.includes(current)) el.value = current;
  }

  // --- bounds helper (no turf) ---
  function extendBoundsWithCoords(bounds, coords) {
    // coords can be [lng,lat] or nested arrays
    if (!coords) return bounds;
    if (typeof coords[0] === "number" && typeof coords[1] === "number") {
      bounds.extend([coords[0], coords[1]]);
      return bounds;
    }
    if (Array.isArray(coords)) {
      for (const c of coords) extendBoundsWithCoords(bounds, c);
    }
    return bounds;
  }

  function boundsForFeatures(features) {
    let b = null;
    for (const f of features) {
      const g = f?.geometry;
      if (!g || !g.coordinates) continue;
      if (!b) {
        // init with a dummy point then extend
        b = new mapboxgl.LngLatBounds([0, 0], [0, 0]);
        // reset immediately by extending with first real coord
        // (will be overwritten by first extend)
        b = new mapboxgl.LngLatBounds();
      }
      extendBoundsWithCoords(b, g.coordinates);
    }
    return b;
  }

  // --- Mapbox: source + layers ---
  const SRC_ID = "tours";
  const LINE_LAYER_ID = "tours-line";
  const POINT_LAYER_ID = "tours-point";

  function ensureSourceAndLayers() {
    if (!map.getSource(SRC_ID)) {
      map.addSource(SRC_ID, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] }
      });
    }

    // line layer (LineString + MultiLineString)
    if (!map.getLayer(LINE_LAYER_ID)) {
      map.addLayer({
        id: LINE_LAYER_ID,
        type: "line",
        source: SRC_ID,
        filter: ["any",
          ["==", ["geometry-type"], "LineString"],
          ["==", ["geometry-type"], "MultiLineString"]
        ],
        paint: {
          "line-color": [
            "case",
            ["any",
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "up"],
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "ascent"]
            ],
            "#1f6feb",
            ["any",
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "down"],
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "descent"]
            ],
            "#b64a4a",
            ["any",
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "traverse"],
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "cross"]
            ],
            "#b000b5",
            "#1f6feb"
          ],
          "line-width": 4,
          "line-opacity": 0.9
        }
      });
    }

    // point layer (Point + MultiPoint)
    if (!map.getLayer(POINT_LAYER_ID)) {
      map.addLayer({
        id: POINT_LAYER_ID,
        type: "circle",
        source: SRC_ID,
        filter: ["any",
          ["==", ["geometry-type"], "Point"],
          ["==", ["geometry-type"], "MultiPoint"]
        ],
        paint: {
          "circle-radius": 7,
          "circle-color": [
            "case",
            ["any",
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "up"],
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "ascent"]
            ],
            "#1f6feb",
            ["any",
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "down"],
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "descent"]
            ],
            "#b64a4a",
            ["any",
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "traverse"],
              ["==", ["downcase", ["coalesce", ["get", "direction"], ["get", "direcrtion"], ""]], "cross"]
            ],
            "#b000b5",
            "#1f6feb"
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
          "circle-opacity": 0.95
        }
      });
    }

    // cursor feedback
    map.on("mouseenter", LINE_LAYER_ID, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", LINE_LAYER_ID, () => (map.getCanvas().style.cursor = ""));
    map.on("mouseenter", POINT_LAYER_ID, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", POINT_LAYER_ID, () => (map.getCanvas().style.cursor = ""));
  }

  function setSourceData(features) {
    const src = map.getSource(SRC_ID);
    if (!src) return;
    src.setData({ type: "FeatureCollection", features });
  }

  function popupHtml(p) {
    const dir = p.direction || p.direcrtion || "";
    const title = p.title ?? p.slug ?? "Tour";

    const lines = [
      `<b>${escapeHtml(title)}</b>`,
      p.region ? escapeHtml(p.region) : "",
      dir ? escapeHtml(dir) : "",
      p.vert_m != null ? `Vert: ${escapeHtml(String(p.vert_m))} m` : "",
      p.distance_km != null ? `Dist: ${escapeHtml(String(p.distance_km))} km` : "",
      p.gpx ? `<a href="${escapeAttr(p.gpx)}" target="_blank" rel="noopener">Download GPX</a>` : ""
    ].filter(Boolean);

    return lines.join("<br>");
  }

  function escapeHtml(s) {
    return String(s)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttr(s) {
    // minimal attribute escaping
    return String(s).replaceAll('"', "%22");
  }

  function wireClicks() {
    const clickHandler = (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties || {};

      // popup
      new mapboxgl.Popup({ closeButton: true, offset: 10 })
        .setLngLat(e.lngLat)
        .setHTML(popupHtml(p))
        .addTo(map);

      // open tour page
      openTour(p);
    };

    map.on("click", LINE_LAYER_ID, clickHandler);
    map.on("click", POINT_LAYER_ID, clickHandler);
  }

  function enable3DTerrain() {
    if (!ENABLE_3D_TERRAIN) return;

    if (!map.getSource("mapbox-dem")) {
      map.addSource("mapbox-dem", {
        type: "raster-dem",
        url: DEM_SOURCE_URL,
        tileSize: 512,
        maxzoom: 14
      });
    }
    map.setTerrain({ source: "mapbox-dem", exaggeration: TERRAIN_EXAGGERATION });

    // Optional sky (looks nice when pitched)
    if (!map.getLayer("sky")) {
      map.addLayer({
        id: "sky",
        type: "sky",
        paint: {
          "sky-type": "atmosphere",
          "sky-atmosphere-sun": [0.0, 0.0],
          "sky-atmosphere-sun-intensity": 10
        }
      });
    }
  }

  function applyFiltersAndRender() {
    const filtered = allFeatures.filter((f) => passesFilters(f.properties || {}));
    setSourceData(filtered);
  }

  

  function wireFilterControls() {
    $("q")?.addEventListener("input", applyFiltersAndRender);
    $("province")?.addEventListener("change", applyFiltersAndRender);
    $("region")?.addEventListener("change", applyFiltersAndRender);

    $("fit")?.addEventListener("click", () => {
      const filtered = allFeatures.filter((f) => passesFilters(f.properties || {}));
      const b = boundsForFeatures(filtered);
      if (b && !b.isEmpty?.()) {
        map.fitBounds(b, { padding: 60, duration: 400 });
      }
    });
  }

  async function loadGeoJSON() {
    try {
      const res = await fetch(DATA_URL, { cache: "no-store" });
      if (!res.ok) return;

      const gj = await res.json();
      allFeatures = (gj.features || []).filter(Boolean);

      // Build filter options
      const props = allFeatures.map((f) => f.properties || {});
      const provinces = uniqSorted(props.map((p) => p.province).map(String));
      const regions = uniqSorted(props.map((p) => p.region).map(String));

      populateSelect("province", provinces, "All provinces");
      populateSelect("region", regions, "All regions");

      applyFiltersAndRender();

      // initial fit (all tours)
      const b = boundsForFeatures(allFeatures);
      if (b && !b.isEmpty?.()) {
        map.fitBounds(b, { padding: 60, duration: 0 });
      }
    } catch (e) {
      console.error(e);
    }
  }

  function initMap() {
    const token = window.MAPBOX_TOKEN;
    if (!token) {
      console.error("MAPBOX_TOKEN missing. Ensure ./js/mapbox_token.js sets window.MAPBOX_TOKEN = 'pk...';");
    }
    mapboxgl.accessToken = token || "";

    map = new mapboxgl.Map({
      container: "map",
      style: MAP_STYLE,
      center: [-122.95, 50.12],
      zoom: 9,
      // give it a nice 3D-ish viewing angle if terrain is enabled
      pitch: ENABLE_3D_TERRAIN ? 55 : 0,
      bearing: ENABLE_3D_TERRAIN ? -15 : 0,
      antialias: true
    });

    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-right");
    
        // Allow external code (e.g. guide.html) to request a resize after smooth scroll
    window.addEventListener("map:resize", () => {
      try { map?.resize?.(); } catch {}
    });


    map.on("load", () => {
      enable3DTerrain();
      ensureSourceAndLayers();
      wireClicks();
      loadGeoJSON();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initMap();
    wireFilterControls();
  });
})();
