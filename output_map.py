"""
output_map.py  -  Generate a self-contained HTML map for the travel itinerary.

Called at the end of travel_agent.py. Writes itinerary_map.html next to the
script, then opens it in the default browser automatically.
"""

import json
import os
import webbrowser
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# City coordinates  (lat/lon for the world map projection)
# ─────────────────────────────────────────────────────────────────────────────

CITY_COORDS: dict[str, tuple[float, float]] = {
    "boston": (42.36, -71.06), "new york": (40.71, -74.01),
    "new york city": (40.71, -74.01), "los angeles": (34.05, -118.24),
    "san francisco": (37.77, -122.42), "chicago": (41.88, -87.63),
    "miami": (25.76, -80.19), "seattle": (47.61, -122.33),
    "washington": (38.91, -77.04), "washington dc": (38.91, -77.04),
    "las vegas": (36.17, -115.14), "toronto": (43.65, -79.38),
    "montreal": (45.50, -73.57), "vancouver": (49.25, -123.12),
    "mexico city": (19.43, -99.13), "cancun": (21.16, -86.85),
    "london": (51.51, -0.13), "paris": (48.86, 2.35),
    "rome": (41.90, 12.49), "amsterdam": (52.37, 4.90),
    "berlin": (52.52, 13.41), "madrid": (40.42, -3.70),
    "barcelona": (41.39, 2.16), "lisbon": (38.72, -9.14),
    "frankfurt": (50.11, 8.68), "zurich": (47.38, 8.54),
    "vienna": (48.21, 16.37), "brussels": (50.85, 4.35),
    "stockholm": (59.33, 18.07), "oslo": (59.91, 10.75),
    "copenhagen": (55.68, 12.57), "helsinki": (60.17, 24.94),
    "athens": (37.98, 23.73), "istanbul": (41.01, 28.95),
    "dublin": (53.33, -6.25), "munich": (48.14, 11.58),
    "milan": (45.46, 9.19), "venice": (45.44, 12.32),
    "prague": (50.08, 14.44), "budapest": (47.50, 19.04),
    "warsaw": (52.23, 21.01), "nice": (43.70, 7.27),
    "edinburgh": (55.95, -3.19),
    "tokyo": (35.68, 139.69), "osaka": (34.69, 135.50),
    "beijing": (39.91, 116.39), "shanghai": (31.23, 121.47),
    "hong kong": (22.32, 114.17), "singapore": (1.35, 103.82),
    "bangkok": (13.75, 100.52), "seoul": (37.57, 126.98),
    "taipei": (25.05, 121.53), "kuala lumpur": (3.14, 101.69),
    "jakarta": (-6.21, 106.85), "manila": (14.60, 120.98),
    "delhi": (28.66, 77.23), "mumbai": (19.08, 72.88),
    "dubai": (25.20, 55.27), "abu dhabi": (24.47, 54.37),
    "doha": (25.29, 51.53), "tel aviv": (32.09, 34.79),
    "cairo": (30.04, 31.24), "nairobi": (-1.29, 36.82),
    "johannesburg": (-26.20, 28.04), "cape town": (-33.93, 18.42),
    "casablanca": (33.59, -7.62), "lagos": (6.52, 3.38),
    "sydney": (-33.87, 151.21), "melbourne": (-37.81, 144.96),
    "auckland": (-36.87, 174.77), "perth": (-31.95, 115.86),
    "sao paulo": (-23.55, -46.63), "rio de janeiro": (-22.91, -43.17),
    "buenos aires": (-34.61, -58.38), "bogota": (4.71, -74.07),
    "lima": (-12.05, -77.04), "santiago": (-33.46, -70.65),
}

STOP_COLORS = ["#888780", "#D85A30", "#1D9E75", "#378ADD",
               "#D4537E", "#BA7517", "#534AB7", "#639922"]


def get_coords(city: str) -> tuple[float, float]:
    return CITY_COORDS.get(city.lower(), (0.0, 0.0))


# ─────────────────────────────────────────────────────────────────────────────
# Build the itinerary data dict from travel_agent objects
# ─────────────────────────────────────────────────────────────────────────────

def build_map_data(
    start_city: str,
    optimised_order: list[str],
    city_plans: dict,
    return_flight,
    budget: float,
    outbound_flight_cost: float,
    return_flight_cost: float,
    total_flight_cost: float,
    total_hotel_cost: float,
    total_attraction_spend: float,
    total_spent: float,
    remaining_budget: float,
) -> dict:
    home_lat, home_lon = get_coords(start_city)

    cities = [{
        "name": start_city,
        "stop": 0,
        "lat": home_lat,
        "lon": home_lon,
        "isHome": True,
        "color": "#5F5E5A",
    }]

    for i, city_name in enumerate(optimised_order):
        plan = city_plans[city_name]
        lat, lon = get_coords(city_name)
        color = STOP_COLORS[(i + 1) % len(STOP_COLORS)]

        flight_info = None
        if plan.flight:
            f = plan.flight
            flight_info = {
                "from": f.origin_airport.iata_code,
                "to": f.destination_airport.iata_code,
                "fromName": f.origin_airport.name,
                "toName": f.destination_airport.name,
                "airline": f.airline,
                "fn": f.flight_number,
                "dep": f.departure_time,
                "arr": f.arrival_time,
                "dur": f"{f.duration:.1f}h",
                "stops": f"{f.stops} stop{'s' if f.stops != 1 else ''}" if f.stops else "non-stop",
                "price": f.price,
            }

        attractions = []
        for attr in plan.attractions:
            cost_str = "Free" if attr.est_cost == 0 else f"~${attr.est_cost:.0f}"
            attractions.append({
                "name": attr.name,
                "rating": round(attr.rating, 1),
                "reviews": attr.review_count,
                "cost": cost_str,
                "score": round(attr.score, 2),
            })

        cities.append({
            "name": city_name,
            "stop": i + 1,
            "lat": lat,
            "lon": lon,
            "isHome": False,
            "color": color,
            "days": plan.days,
            "flight": flight_info,
            "hotel": {
                "rate": plan.hotel_nightly_rate,
                "nights": plan.days,
                "total": plan.hotel_total_cost,
            },
            "attractions": attractions,
            "attrSpend": plan.attraction_budget_spent,
        })

    return_info = None
    if return_flight:
        rf = return_flight
        return_info = {
            "from": rf.origin_airport.iata_code,
            "to": rf.destination_airport.iata_code,
            "airline": rf.airline,
            "fn": rf.flight_number,
            "dep": rf.departure_time,
            "arr": rf.arrival_time,
            "dur": f"{rf.duration:.1f}h",
            "stops": f"{rf.stops} stop{'s' if rf.stops != 1 else ''}" if rf.stops else "non-stop",
            "price": rf.price,
        }

    # Minimum budget = flights + hotels + all attraction costs (ignoring budget cap)
    # This is what it costs bare minimum with no leftover
    min_budget = round(total_flight_cost + total_hotel_cost + total_attraction_spend, 2)
    over_budget = total_spent > budget

    return {
        "cities": cities,
        "returnFlight": return_info,
        "budget": {
            "total": budget,
            "outbound": outbound_flight_cost,
            "returnFlight": return_flight_cost,
            "totalFlights": total_flight_cost,
            "hotels": total_hotel_cost,
            "attractions": total_attraction_spend,
            "totalSpent": total_spent,
            "remaining": remaining_budget,
            "overBudget": over_budget,
            "minBudget": min_budget,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# HTML template
# ─────────────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Travel Itinerary Map</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/topojson/3.0.2/topojson.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #f5f4f0; color: #222; font-size: 14px; }
  #app { display: flex; flex-direction: column; gap: 16px; padding: 16px; max-width: 1400px; margin: 0 auto; }
  h1 { font-size: 18px; font-weight: 500; color: #222; padding: 8px 0 0; }
  #top { display: flex; gap: 16px; align-items: flex-start; }
  #map-wrap { flex: 1; min-width: 0; border: 1px solid #ddd; border-radius: 12px;
              overflow: hidden; background: #dbeef5; position: relative; box-shadow: 0 1px 4px rgba(0,0,0,0.07); }
  #map { display: block; width: 100%; }
  #sidebar { width: 280px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px; }
  .city-card { background: #fff; border: 1px solid #e0dfd8; border-radius: 12px; padding: 12px 14px; }
  .city-card h3 { font-size: 13px; font-weight: 500; color: #222; margin-bottom: 8px;
                  display: flex; align-items: center; gap: 6px; }
  .stop-badge { width: 22px; height: 22px; border-radius: 50%; display: inline-flex;
                align-items: center; justify-content: center; font-size: 11px;
                font-weight: 500; flex-shrink: 0; color: white; }
  .attr-list { list-style: none; }
  .attr-list li { font-size: 11px; color: #555; padding: 3px 0; display: flex;
                  justify-content: space-between; border-bottom: 0.5px solid #eee; }
  .attr-list li:last-child { border-bottom: none; }
  .attr-rank { width: 16px; color: #aaa; flex-shrink: 0; font-size: 10px; }
  .attr-name { flex: 1; padding-right: 6px; }
  .attr-cost { flex-shrink: 0; color: #888; font-size: 10px; }
  .city-footer { margin-top: 8px; font-size: 11px; color: #777; display: flex;
                 justify-content: space-between; padding-top: 6px;
                 border-top: 0.5px solid #eee; }
  #budget-box { background: #fff; border: 1px solid #e0dfd8; border-radius: 12px; padding: 16px 18px; }
  #budget-box h2 { font-size: 14px; font-weight: 500; color: #222; margin-bottom: 12px; }
  .budget-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 32px; margin-bottom: 12px; }
  .b-row { display: flex; justify-content: space-between; font-size: 12px; color: #555;
           padding: 3px 0; border-bottom: 0.5px solid #f0ede8; }
  .b-row:last-child { border-bottom: none; }
  .b-val { font-weight: 500; color: #222; }
  .b-divider { border: none; border-top: 1px solid #ddd; margin: 8px 0; }
  .b-totals { display: grid; grid-template-columns: 1fr 1fr; gap: 0 32px; }
  .b-total-row { display: flex; justify-content: space-between; font-size: 13px;
                 font-weight: 500; color: #222; padding: 2px 0; }
  .b-remaining { color: #1D9E75; }
  .day-breakdown { margin-top: 12px; padding-top: 12px; border-top: 1px solid #eee; }
  .day-breakdown h3 { font-size: 12px; font-weight: 500; color: #666; margin-bottom: 8px; }
  .day-rows { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 4px; }
  .day-row { display: flex; align-items: center; justify-content: space-between;
             font-size: 11px; color: #555; padding: 3px 6px; background: #f9f8f5;
             border-radius: 6px; }
  .day-row-left { display: flex; align-items: center; gap: 6px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .tooltip { position: absolute; background: #fff; border: 1px solid #ddd; border-radius: 8px;
             padding: 10px 12px; font-size: 11px; color: #222; pointer-events: none;
             z-index: 100; width: 210px; box-shadow: 0 4px 12px rgba(0,0,0,0.12); display: none; }
  .tooltip h4 { font-size: 12px; font-weight: 500; margin-bottom: 6px; color: #222; }
  .t-row { display: flex; justify-content: space-between; color: #666; padding: 2px 0;
           border-bottom: 0.5px solid #f0f0f0; }
  .t-row:last-child { border-bottom: none; }
  .t-row span:last-child { font-weight: 500; color: #222; }
  .legend { position: absolute; bottom: 10px; left: 10px; background: rgba(255,255,255,0.9);
            border-radius: 6px; padding: 6px 8px; font-size: 10px; color: #555; }
  .legend-item { display: flex; align-items: center; gap: 5px; margin: 2px 0; }
  .legend-line { width: 18px; height: 2px; background: #888; }
  .legend-dash { width: 18px; height: 2px; background: repeating-linear-gradient(
    to right, #888 0, #888 4px, transparent 4px, transparent 7px); }
  @media (max-width: 900px) {
    #top { flex-direction: column; }
    #sidebar { width: 100%; }
    .budget-grid, .b-totals { grid-template-columns: 1fr; }
  }
  #modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.45);
                   z-index: 1000; align-items: center; justify-content: center; }
  #modal-overlay.visible { display: flex; }
  #modal-box { background: #fff; border-radius: 14px; padding: 28px 32px; max-width: 420px;
               width: 90%; box-shadow: 0 8px 32px rgba(0,0,0,0.18); text-align: center; }
  #modal-box .modal-icon { font-size: 36px; margin-bottom: 12px; }
  #modal-box h2 { font-size: 17px; font-weight: 500; color: #222; margin-bottom: 10px; }
  #modal-box p { font-size: 13px; color: #555; line-height: 1.6; margin-bottom: 6px; }
  #modal-box .modal-min { font-size: 26px; font-weight: 500; color: #D85A30; margin: 14px 0; }
  #modal-box .modal-breakdown { font-size: 12px; color: #777; margin-bottom: 18px;
                                 background: #f9f8f5; border-radius: 8px; padding: 10px 14px;
                                 text-align: left; }
  #modal-box .modal-breakdown div { display: flex; justify-content: space-between; padding: 2px 0; }
  #modal-box .modal-breakdown .mb-val { font-weight: 500; color: #444; }
  #modal-box button { background: #222; color: #fff; border: none; border-radius: 8px;
                      padding: 10px 28px; font-size: 13px; cursor: pointer; font-weight: 500; }
  #modal-box button:hover { background: #444; }
</style>
</head>
<body>
<div id="modal-overlay" id="modal-overlay">
  <div id="modal-box">
    <div class="modal-icon">&#9888;</div>
    <h2>Over budget</h2>
    <p>Your selected itinerary exceeds your budget of <strong id="modal-user-budget"></strong>.</p>
    <div class="modal-min" id="modal-min-value"></div>
    <p style="font-size:12px;color:#888;margin-bottom:12px;">minimum required budget</p>
    <div class="modal-breakdown" id="modal-breakdown"></div>
    <button onclick="document.getElementById('modal-overlay').classList.remove('visible')">View map anyway</button>
  </div>
</div>
<div id="app">
  <h1>Travel Itinerary Map</h1>
  <div id="top">
    <div id="map-wrap">
      <svg id="map" viewBox="0 0 900 460"></svg>
      <div class="tooltip" id="tooltip"></div>
      <div class="legend">
        <div class="legend-item"><div class="legend-line"></div><span>Outbound leg</span></div>
        <div class="legend-item"><div class="legend-dash"></div><span>Return home</span></div>
      </div>
    </div>
    <div id="sidebar"><div id="cards"></div></div>
  </div>
  <div id="budget-box">
    <h2>Budget breakdown</h2>
    <div class="budget-grid">
      <div id="bc-left"></div>
      <div id="bc-right"></div>
    </div>
    <hr class="b-divider">
    <div class="b-totals">
      <div class="b-total-row"><span>Total estimated spend</span><span id="b-total"></span></div>
      <div class="b-total-row b-remaining"><span>Remaining budget</span><span id="b-remaining"></span></div>
    </div>
    <div class="day-breakdown">
      <h3>Day breakdown</h3>
      <div class="day-rows" id="day-rows"></div>
    </div>
  </div>
</div>

<script>
const DATA = __DATA_PLACEHOLDER__;

function fmt(n) { return "$" + n.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2}); }

function buildSidebar() {
  const container = document.getElementById("cards");
  DATA.cities.filter(c => !c.isHome).forEach(city => {
    const card = document.createElement("div");
    card.className = "city-card";
    const rows = city.attractions.map((a, i) =>
      `<li>
        <span class="attr-rank">${i+1}.</span>
        <span class="attr-name">${a.name}</span>
        <span class="attr-cost">${a.cost}</span>
      </li>`
    ).join("");
    card.innerHTML = `
      <h3>
        <span class="stop-badge" style="background:${city.color}">${city.stop}</span>
        ${city.name} &mdash; ${city.days} day${city.days !== 1 ? "s" : ""}
      </h3>
      <ul class="attr-list">${rows}</ul>
      <div class="city-footer">
        <span>Hotel: ${city.hotel.rate > 0 ? fmt(city.hotel.rate) + "/night" : "no data"}</span>
        <span>Attractions: ~${fmt(city.attrSpend)}</span>
      </div>`;
    container.appendChild(card);
  });
}

function buildBudget() {
  const b = DATA.budget;
  document.getElementById("bc-left").innerHTML = `
    <div class="b-row"><span>Outbound flights</span><span class="b-val">${fmt(b.outbound)}</span></div>
    <div class="b-row"><span>Return flight</span><span class="b-val">${fmt(b.returnFlight)}</span></div>
    <div class="b-row"><span>Total flights</span><span class="b-val">${fmt(b.totalFlights)}</span></div>`;
  document.getElementById("bc-right").innerHTML = `
    <div class="b-row"><span>Hotel stays</span><span class="b-val">${fmt(b.hotels)}</span></div>
    <div class="b-row"><span>Est. attractions</span><span class="b-val">${fmt(b.attractions)}</span></div>`;
  document.getElementById("b-total").textContent = fmt(b.totalSpent);
  document.getElementById("b-remaining").textContent = fmt(b.remaining);

  const dr = document.getElementById("day-rows");
  DATA.cities.filter(c => !c.isHome).forEach(city => {
    const row = document.createElement("div");
    row.className = "day-row";
    row.innerHTML = `
      <div class="day-row-left">
        <div class="dot" style="background:${city.color}"></div>
        <span style="font-weight:500">${city.name}</span>
        <span>${city.days} day${city.days !== 1 ? "s" : ""}</span>
      </div>
      <div style="display:flex;gap:10px;color:#888">
        <span>hotel ~${fmt(city.hotel.total)}</span>
        <span>attr ~${fmt(city.attrSpend)}</span>
      </div>`;
    dr.appendChild(row);
  });

  if (DATA.returnFlight) {
    const row = document.createElement("div");
    row.className = "day-row";
    const last = DATA.cities.filter(c => !c.isHome).slice(-1)[0];
    const home = DATA.cities.find(c => c.isHome);
    row.innerHTML = `
      <div class="day-row-left">
        <div class="dot" style="background:#888;border:1px dashed #555"></div>
        <span style="font-weight:500">Return</span>
        <span>${last.name} &rarr; ${home.name}</span>
      </div>
      <div style="color:#888">${DATA.returnFlight.dur} travel</div>`;
    dr.appendChild(row);
  }
}

function drawMap() {
  const svg = d3.select("#map");
  const W = 900, H = 460;

  const projection = d3.geoNaturalEarth1().scale(153).translate([W/2, H/2]);
  const path = d3.geoPath().projection(projection);

  fetch("https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json")
    .then(r => r.json())
    .then(world => {
      svg.append("rect").attr("width", W).attr("height", H).attr("fill", "#dbeef5");
      const countries = topojson.feature(world, world.objects.countries);
      svg.append("g").selectAll("path").data(countries.features).join("path")
        .attr("d", path).attr("fill", "#e8e6df").attr("stroke", "#c8c6be").attr("stroke-width", 0.4);
      renderOverlay(svg, projection);
    })
    .catch(() => {
      svg.append("rect").attr("width", W).attr("height", H).attr("fill", "#dbeef5");
      renderOverlay(svg, projection);
    });
}

function renderOverlay(svg, proj) {
  const stops = DATA.cities.filter(c => !c.isHome);
  const home = DATA.cities.find(c => c.isHome);
  const tooltip = document.getElementById("tooltip");
  const wrap = document.getElementById("map-wrap");

  function px(city) { return proj([city.lon, city.lat]); }

  const legs = [
    { from: home, to: stops[0], isReturn: false },
    ...stops.slice(0, -1).map((c, i) => ({ from: c, to: stops[i+1], isReturn: false })),
    ...(DATA.returnFlight ? [{ from: stops[stops.length-1], to: home, isReturn: true }] : [])
  ];

  legs.forEach(leg => {
    const [ax, ay] = px(leg.from);
    const [bx, by] = px(leg.to);
    const mx = (ax + bx) / 2;
    const my = (ay + by) / 2 - 45;
    svg.append("path")
      .attr("d", `M${ax},${ay} Q${mx},${my} ${bx},${by}`)
      .attr("fill", "none")
      .attr("stroke", leg.isReturn ? "#888" : leg.to.color)
      .attr("stroke-width", leg.isReturn ? 1.5 : 2)
      .attr("stroke-dasharray", leg.isReturn ? "5,4" : "none")
      .attr("opacity", 0.75);
  });

  DATA.cities.forEach(city => {
    const [cx, cy] = proj([city.lon, city.lat]);
    if (city.isHome) {
      svg.append("circle").attr("cx", cx).attr("cy", cy).attr("r", 7)
        .attr("fill", "#5F5E5A").attr("stroke", "#fff").attr("stroke-width", 1.5).attr("opacity", 0.9);
      svg.append("text").attr("x", cx).attr("y", cy - 12)
        .attr("text-anchor", "middle").attr("fill", "#333")
        .attr("font-size", 11).attr("font-weight", "500").text(city.name);
    } else {
      const g = svg.append("g").style("cursor", "pointer");
      g.append("circle").attr("cx", cx).attr("cy", cy).attr("r", 13)
        .attr("fill", city.color).attr("stroke", "#fff").attr("stroke-width", 2).attr("opacity", 0.9);
      g.append("text").attr("x", cx).attr("y", cy + 5)
        .attr("text-anchor", "middle").attr("fill", "white")
        .attr("font-size", 11).attr("font-weight", "500").text(city.stop);
      svg.append("text").attr("x", cx).attr("y", cy - 17)
        .attr("text-anchor", "middle").attr("fill", "#222")
        .attr("font-size", 11).attr("font-weight", "500").text(city.name);

      g.on("mouseenter", function(event) {
        const svgEl = document.getElementById("map");
        const svgRect = svgEl.getBoundingClientRect();
        const wrapRect = wrap.getBoundingClientRect();
        const scaleX = svgRect.width / 900;
        const scaleY = svgRect.height / 460;
        const px2 = cx * scaleX + (svgRect.left - wrapRect.left);
        const py2 = cy * scaleY + (svgRect.top - wrapRect.top);
        const f = city.flight;
        tooltip.innerHTML = `
          <h4>Stop ${city.stop}: ${city.name}</h4>
          ${f ? `
          <div class="t-row"><span>Flight</span><span>${f.fn}</span></div>
          <div class="t-row"><span>Airline</span><span>${f.airline}</span></div>
          <div class="t-row"><span>Route</span><span>${f.from} &rarr; ${f.to}</span></div>
          <div class="t-row"><span>Departs</span><span>${f.dep}</span></div>
          <div class="t-row"><span>Arrives</span><span>${f.arr}</span></div>
          <div class="t-row"><span>Duration</span><span>${f.dur} (${f.stops})</span></div>
          <div class="t-row"><span>Flight price</span><span>${fmt(f.price)}</span></div>
          ` : ""}
          <div class="t-row"><span>Hotel/night</span><span>${city.hotel.rate > 0 ? fmt(city.hotel.rate) : "N/A"}</span></div>
          <div class="t-row"><span>Hotel total</span><span>${fmt(city.hotel.total)} (${city.hotel.nights}n)</span></div>
          <div class="t-row"><span>Attractions</span><span>~${fmt(city.attrSpend)}</span></div>`;
        const tw = 210, th = 230;
        let left = px2 + 16, top = py2 - 30;
        if (left + tw > wrapRect.width - 8) left = px2 - tw - 16;
        if (top + th > wrapRect.height - 8) top = wrapRect.height - th - 8;
        if (top < 8) top = 8;
        tooltip.style.left = left + "px";
        tooltip.style.top = top + "px";
        tooltip.style.display = "block";
      });
      g.on("mouseleave", () => { tooltip.style.display = "none"; });
    }
  });
}

buildSidebar();
buildBudget();
drawMap();

if (DATA.budget.overBudget) {
  const b = DATA.budget;
  document.getElementById("modal-user-budget").textContent = fmt(b.total);
  document.getElementById("modal-min-value").textContent = fmt(b.minBudget);
  document.getElementById("modal-breakdown").innerHTML = `
    <div><span>Flights</span><span class="mb-val">${fmt(b.totalFlights)}</span></div>
    <div><span>Hotels</span><span class="mb-val">${fmt(b.hotels)}</span></div>
    <div><span>Attractions</span><span class="mb-val">${fmt(b.attractions)}</span></div>
  `;
  document.getElementById("modal-overlay").classList.add("visible");
}
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_map(data: dict, output_path: str = None) -> str:
    """
    Write the itinerary HTML file and open it in the default browser.
    Returns the path to the written file.
    """
    if output_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, "itinerary_map.html")

    json_data = json.dumps(data, ensure_ascii=False, indent=2)
    html = HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", json_data)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n  Map saved to: {output_path}")
    webbrowser.open(f"file://{output_path}")
    return output_path