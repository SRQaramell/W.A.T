from flask import Flask, render_template, request, jsonify
from dataclasses import dataclass, asdict
from typing import List
import itertools

# >>> KORZYSTAMY Z TWOJEGO elevation.py <<<
from pyhigh import get_elevation, get_elevation_batch

app = Flask(__name__)

# ======= MODELE =======
@dataclass
class AntennaModel:
    id: int
    name: str
    lat: float
    lng: float
    height: float
    radius: float
    battery: float
    category: int

ANTENNAS: List[AntennaModel] = []
_id_counter = itertools.count(1)

# ======= WIDOK FRONTU =======
@app.get("/index")
@app.get("/menu")
def main_menu():
    return render_template("index.html")

# Możesz też przekierować "/" na menu:
@app.get("/")
def home_redirect():
    return render_template("index.html")

# I dodać osobny widok dla mapy:
@app.get("/map")
def map_view():
    return render_template("map.html")
@app.get("/settings")
def settings_view():
    return render_template("settings.html")  # nazwa pliku w templates/

# ======= API =======
@app.get("/api/antennas")
def get_antennas():
    return jsonify([asdict(a) for a in ANTENNAS])

@app.post("/api/antennas")
def create_antenna():
    data = request.get_json(force=True)
    lat = float(data["lat"])
    lng = float(data["lng"])
    radius = float(data.get("radius", 300))
    category = int(data.get("category", 5))
    battery = float(data.get("battery", 100))
    name = data.get("name") or f"Antenna {len(ANTENNAS)+1}"

    # --- wysokość terenu z elevation.py ---
    # Możesz użyć pojedynczego punktu:
    # elevation_m = get_elevation(lat, lng, "Eurasia")
    # Albo wersji wsadowej (tu z jednym punktem), łatwiej potem rozszerzyć:
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
        category=category
    )
    ANTENNAS.append(antenna)
    print("created antenna:", ANTENNAS)
    return jsonify(asdict(antenna)), 201

@app.delete("/api/antennas/<int:antenna_id>")
def delete_antenna(antenna_id: int):
    global ANTENNAS
    before = len(ANTENNAS)
    ANTENNAS = [a for a in ANTENNAS if a.id != antenna_id]
    return ("", 204) if len(ANTENNAS) < before else (jsonify({"error": "not found"}), 404)

# (opcjonalnie) prosty endpoint do testu wysokości
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
