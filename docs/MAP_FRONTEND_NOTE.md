# Map + routing frontend note (for Ee)

The backend map/routing piece is done. This is how to draw it with **MapLibre GL +
OpenStreetMap tiles**. **No API key anywhere** — not for the map, not for routing.

## 1. The endpoint

Call **`POST /care/map`** (same body as `/care`). There is also an alias at
`POST /api/care/map`.

Request body:

```json
{ "assessment": <RiskAssessment>, "user_lat": 42.3601, "user_lon": -71.0589, "max_results": 5 }
```

Response (plain JSON — `/care` is unchanged, this is the map-enriched sibling):

```json
{
  "care": { "recommendations": [ ...FacilityRecommendation... ], "care_tier": "Elevated", "disclaimer": "..." },
  "map": {
    "user": { "lat": 42.3601, "lon": -71.0589 },
    "pins": [
      { "facility_id": "...", "name": "Massachusetts General Hospital",
        "lat": 42.363206, "lon": -71.068772,
        "drive_minutes": 2.9, "rank_score": 0.72, "is_top": true },
      ...
    ],
    "route_to_top": {
      "source": "live-osrm",            // or "estimated-haversine" if OSRM was down
      "drive_minutes": 2.9,
      "distance_km": 1.2,
      "geometry": { "type": "LineString", "coordinates": [[lon,lat], ...] },
      "estimated": false,
      "note": "Live driving route from the OSRM public server (OpenStreetMap).",
      "to_facility_id": "...", "to_name": "Massachusetts General Hospital"
    },
    "tiles": {
      "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      "attribution": "© OpenStreetMap contributors",
      "max_zoom": 19
    }
  }
}
```

`map.route_to_top` is `null` only when no facility has coordinates (e.g. care
paused for a travel window) — then just show pins and no route.

## 2. Free tiles — MapLibre base map (no key)

MapLibre normally wants a vector style URL (which often needs a key). Skip that:
use the **raster OSM tiles** from `map.tiles` as a single raster source. No token.

```js
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// tiles = resp.map.tiles
const map = new maplibregl.Map({
  container: "map",
  center: [resp.map.user.lon, resp.map.user.lat], // MapLibre is [lon, lat]
  zoom: 10,
  style: {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: [resp.map.tiles.url],         // https://tile.openstreetmap.org/{z}/{x}/{y}.png
        tileSize: 256,
        attribution: resp.map.tiles.attribution,
        maxzoom: resp.map.tiles.max_zoom,
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  },
});
```

Install: `npm i maplibre-gl` — that's the only dependency, and it's free/OSS.

## 3. Pins

`map.pins` is already ranked (same order as `care.recommendations`). Each pin has
`lat`, `lon`, `name`, `drive_minutes`, and `is_top`. **MapLibre coordinates are
`[lon, lat]`** — longitude first.

```js
for (const pin of resp.map.pins) {
  new maplibregl.Marker({ color: pin.is_top ? "#2a7" : "#888" })
    .setLngLat([pin.lon, pin.lat])
    .setPopup(new maplibregl.Popup().setText(
      `${pin.name} — ~${pin.drive_minutes ?? "?"} min`
    ))
    .addTo(map);
}
// user location
new maplibregl.Marker({ color: "#36c" })
  .setLngLat([resp.map.user.lon, resp.map.user.lat]).addTo(map);
```

## 4. The route line

`map.route_to_top.geometry` is already a **GeoJSON LineString in `[lon, lat]`
order** — feed it straight to a MapLibre line layer. Works the same whether it's
a live OSRM road path (many points) or the straight-line estimate (2 points).

```js
const rt = resp.map.route_to_top;
if (rt) {
  map.addSource("route", { type: "geojson",
    data: { type: "Feature", geometry: rt.geometry, properties: {} } });
  map.addLayer({ id: "route", type: "line", source: "route",
    paint: {
      "line-width": 5,
      // solid for a live route, dashed to signal an estimate
      "line-color": rt.source === "live-osrm" ? "#2a7" : "#e67e22",
      ...(rt.estimated ? { "line-dasharray": [2, 2] } : {}),
    }});
}
```

## 5. Show the source honestly

`route_to_top.source` tells the user whether the time is real:

- `"live-osrm"` → "~29 min drive (live traffic-free routing)"
- `"estimated-haversine"` → "~29 min drive (estimated — live routing was
  unavailable)". `route_to_top.note` has a ready sentence; `estimated` is a bool.

The backend never fails the call because routing is down — it falls back to the
labelled estimate. So `route_to_top` is always drawable; just read `source` to
label it.

## 6. Attribution

OSM tiles require visible attribution. MapLibre renders it from the `attribution`
field above automatically. Keep it — it's the licence condition for the free tiles.
