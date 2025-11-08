from flask import Flask, render_template, request, jsonify
from dataclasses import dataclass, asdict
from typing import List, Optional
import itertools

# Użyj swojego elevation.py (wrapper na pyhigh) – tak jak wcześniej
# Jeśli masz bezpośrednio pyhigh, możesz podmienić importy na:
#   from pyhigh import get_elevation, get_elevation_batch
from pyhigh import get_elevation, get_elevation_batch

app = Flask(__name__)

# ======= MODELE =======
@dataclass
class AntennaModel:
    id: int
    name: str
    lat: float
    lng: float
    height: float         # m n.p.m.
    radius: float         # m
    battery: float        # %
    category: int         # 2/3/4/5 (G)
    antenna_type: str     # 'ogolna' | 'kierunkowa'
    bearing_deg: Optional[float]  # 0..360 (dla kierunkowej)
    beam_width_deg: float         # np. 60 (dla kierunkowej)
    affiliation: str      # 'ally' | 'enemy' | 'neutral'
    role: str             # 'transmission' | 'jamming'

ANTENNAS: List[AntennaModel] = []
_id_counter = itertools.count(1)

# ======= WIDOK =======
@app.get("/")
def map_view():
    return render_template("map.html")

# ======= API =======
@app.get("/api/antennas")
def get_antennas():
    return jsonify([asdict(a) for a in ANTENNAS])

@app.post("/api/antennas")
def create_antenna():
    data = request.get_json(force=True)

    def _f(val, default):
        if val is None or val == "":
            return float(default)
        return float(val)

    def _i(val, default):
        if val is None or val == "":
            return int(default)
        return int(val)

    lat = float(data["lat"])
    lng = float(data["lng"])
    radius = _f(data.get("radius", 300), 300)
    category = _i(data.get("category", 5), 5)
    battery = _f(data.get("battery", 100), 100)
    name = data.get("name") or f"Antenna {len(ANTENNAS)+1}"

    antenna_type = str(data.get("antenna_type", "ogolna")).lower()
    if antenna_type not in ("ogolna", "kierunkowa"):
        return jsonify({"error": "antenna_type must be 'ogolna' or 'kierunkowa'"}), 400

    bw_raw = data.get("beam_width_deg", None)
    beam_width_deg = 60.0 if bw_raw is None or bw_raw == "" else float(bw_raw)

    bearing_deg = data.get("bearing_deg", None)
    if antenna_type == "kierunkowa":
        if bearing_deg is None or bearing_deg == "":
            return jsonify({"error": "kierunkowa wymaga 'bearing_deg' (0..360)"}), 400
        bearing_deg = float(bearing_deg) % 360.0
    else:
        bearing_deg = None

    affiliation = str(data.get("affiliation", "ally")).lower()
    if affiliation not in ("ally", "enemy", "neutral"):
        return jsonify({"error": "affiliation must be 'ally'|'enemy'|'neutral'"}), 400

    role = str(data.get("role", "transmission")).lower()
    if role not in ("transmission", "jamming"):
        return jsonify({"error": "role must be 'transmission'|'jamming'"}), 400

    # Wysokość terenu (pyhigh przez Twój elevation.py)
    try:
        elevs = get_elevation_batch([(lat, lng, "Eurasia")], default_continent="Eurasia")
        elevation_m = float(elevs[0]) if elevs is not None else 0.0
    except Exception as e:
        print("elevation error:", e)
        elevation_m = 0.0

    antenna = AntennaModel(
        id=next(_id_counter),
        name=name,
        lat=lat,
        lng=lng,
        height=elevation_m,
        radius=radius,
        battery=battery,
        category=category,
        antenna_type=antenna_type,
        bearing_deg=bearing_deg,
        beam_width_deg=beam_width_deg,
        affiliation=affiliation,
        role=role
    )
    ANTENNAS.append(antenna)
    return jsonify(asdict(antenna)), 201

@app.delete("/api/antennas/<int:antenna_id>")
def delete_antenna(antenna_id: int):
    global ANTENNAS
    before = len(ANTENNAS)
    ANTENNAS = [a for a in ANTENNAS if a.id != antenna_id]
    return ("", 204) if len(ANTENNAS) < before else (jsonify({"error": "not found"}), 404)

# Debug (opcjonalnie)
@app.get("/api/debug/elevation")
def debug_elevation():
    lat = float(request.args.get("lat", "51.1079"))
    lng = float(request.args.get("lng", "17.0385"))
    try:
        h = get_elevation(lat, lng, "Eurasia")
        return jsonify({"lat": lat, "lng": lng, "elevation_m": float(h)})
    except Exception as e:
        return jsonify({"error": repr(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
