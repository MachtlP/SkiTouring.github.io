// docs/js/main.js
(() => {
  // Adjust if needed:
  const DATA_URL = "data/tours.geojson";

  let map;
  let allFeatures = [];
  let geoLayer = null;

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

  function passesFilters(p) {
    const q = norm($("q")?.value);
    const diff = norm($("difficulty")?.value);
    const act = norm($("activity")?.value);

    const hay =
      `${norm(p.title)} ${norm(p.region)} ${norm(p.subtitle)} ${norm(p.activity)} ${norm(p.difficulty)}`;

    if (q && !hay.includes(q)) return false;
    if (diff && norm(p.difficulty) !== diff) return false;
    if (act && norm(p.activity) !== act) return false;
    return true;
  }

  function renderCards(features) {
    const grid = $("grid");
    const count = $("count");
    if (!grid || !count) return;

    grid.innerHTML = "";

    for (const f of features) {
      const p = f.properties || {};

      const card = document.createElement("div");
      card.className = "card";
      card.addEventListener("click", () => openTour(p));

      const cover = document.createElement("div");
      cover.className = "cover";

      if (p.cover) {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.alt = p.title || "Tour cover";
        img.src = p.cover;
        cover.appendChild(img);
      } else {
        cover.textContent = "No cover";
      }

      const meta = document.createElement("div");
      meta.className = "meta";

      const title = document.createElement("p");
      title.className = "title";
      title.textContent = p.title || p.slug || "Untitled tour";

      const subtitle = document.createElement("p");
      subtitle.className = "subtitle";
      subtitle.textContent = p.region || p.subtitle || "";

      const chips = document.createElement("div");
      chips.className = "chips";

      const addChip = (text) => {
        if (!text && text !== 0) return;
        const c = document.createElement("span");
        c.className = "chip";
        c.textContent = String(text);
        chips.appendChild(c);
      };

      addChip(p.activity);
      addChip(p.difficulty);
      if (p.vert_m != null) addChip(`${p.vert_m} m`);
      if (p.distance_km != null) addChip(`${p.distance_km} km`);

      meta.appendChild(title);
      if (subtitle.textContent) meta.appendChild(subtitle);
      meta.appendChild(chips);

      card.appendChild(cover);
      card.appendChild(meta);
      grid.appendChild(card);
    }

    count.textContent = `${features.length} tours shown`;
  }

  function renderMap(features) {
    if (!map) return;

    if (geoLayer) {
      map.removeLayer(geoLayer);
      geoLayer = null;
    }

    const fc = { type: "FeatureCollection", features };

    geoLayer = L.geoJSON(fc, {
      style: () => ({ weight: 4, opacity: 0.9 }),
      pointToLayer: (feature, latlng) =>
        L.circleMarker(latlng, { radius: 7, weight: 2, opacity: 0.9 }),
      onEachFeature: (feature, layer) => {
        const p = feature.properties || {};
        const html =
          `<b>${p.title ?? p.slug ?? "Tour"}</b>` +
          (p.region ? `<br>${p.region}` : "") +
          (p.vert_m != null ? `<br>Vert: ${p.vert_m} m` : "") +
          (p.distance_km != null ? `<br>Dist: ${p.distance_km} km` : "") +
          (p.gpx ? `<br><a href="${p.gpx}" target="_blank" rel="noopener">Download GPX</a>` : "");

        layer.bindPopup(html);
        layer.on("click", () => openTour(p));
      },
    }).addTo(map);
  }

  function applyFiltersAndRender() {
    const filtered = allFeatures.filter((f) => passesFilters(f.properties || {}));
    renderCards(filtered);
    renderMap(filtered);
  }

  function wireHeroControls() {
    $("ctaBrowse")?.addEventListener("click", () => {
      document.querySelector(".book")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    $("ctaMap")?.addEventListener("click", () => {
      document.querySelector(".mapwrap")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });

    document.querySelectorAll(".toc-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const q = btn.getAttribute("data-q") || "";
        const input = $("q");
        if (input) input.value = q;
        applyFiltersAndRender();
        document.querySelector(".book")?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function wireFilterControls() {
    $("q")?.addEventListener("input", applyFiltersAndRender);
    $("difficulty")?.addEventListener("change", applyFiltersAndRender);
    $("activity")?.addEventListener("change", applyFiltersAndRender);

    $("fit")?.addEventListener("click", () => {
      if (!geoLayer) return;
      try {
        map.fitBounds(geoLayer.getBounds().pad(0.15));
      } catch {
        // ignore
      }
    });
  }

  async function loadGeoJSON() {
    const count = $("count");
    try {
      const res = await fetch(DATA_URL, { cache: "no-store" });
      if (!res.ok) {
        if (count) count.textContent = `Failed to load ${DATA_URL}`;
        return;
      }
      const gj = await res.json();
      allFeatures = (gj.features || []).filter(Boolean);

      applyFiltersAndRender();

      // initial fit
      if (allFeatures.length) {
        try {
          const tmp = L.geoJSON(gj);
          map.fitBounds(tmp.getBounds().pad(0.15));
        } catch {
          // ignore
        }
      }
    } catch (e) {
      if (count) count.textContent = `Failed to load ${DATA_URL}`;
      console.error(e);
    }
  }

  function initMap() {
    map = L.map("map", { zoomControl: true }).setView([50.12, -122.95], 9);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map);
  }

  document.addEventListener("DOMContentLoaded", () => {
    initMap();
    wireHeroControls();
    wireFilterControls();
    loadGeoJSON();
  });
})();
