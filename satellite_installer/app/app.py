from flask import Flask, render_template, request, jsonify
from math import radians, degrees, atan2, cos, sin, sqrt, atan

app = Flask(__name__)

SATELLITES = {
    "astra19": {"name": "Astra 19.2°E", "lon": 19.2, "dish": 60, "tp": "11347 V 22000", "note": "3sat HD / riferimento FTA"},
    "hotbird13": {"name": "Hotbird 13.0°E", "lon": 13.0, "dish": 60, "tp": "10719 V 27500", "note": "DVB-S2 / riferimento puntamento"},
    "thor08w": {"name": "Thor 0.8°W", "lon": -0.8, "dish": 80, "tp": "11823 H 30000", "note": "Verificare il TP in base al bouquet Digi"},
    "eutelsat5w": {"name": "Eutelsat 5°W", "lon": -5.0, "dish": 80, "tp": "11096 V 29950", "note": "Riferimento iniziale"},
}

SYSTEMS = {
    "single": "LNB universale Single",
    "twin": "LNB universale Twin",
    "quad": "LNB universale Quad",
    "octo": "LNB universale Octo",
    "unicable": "SCR / Unicable EN50494",
    "jess": "JESS / dCSS EN50607",
    "quattro": "LNB Quattro + multiswitch",
    "wideband": "LNB Wideband + multiswitch"
}

def look_angles(lat, lon, sat_lon):
    phi = radians(lat)
    dl = radians(sat_lon - lon)
    c = cos(phi) * cos(dl)
    elevation = degrees(atan((c - 0.1512) / sqrt(max(1e-12, 1 - c*c))))
    az = degrees(atan2(sin(dl), -sin(phi) * cos(dl)))
    azimuth = (180 + az) % 360
    skew = degrees(atan2(sin(dl), sin(phi)))
    return round(azimuth, 1), round(elevation, 1), round(skew, 1)

@app.route("/")
def index():
    return render_template("index.html", satellites=SATELLITES, systems=SYSTEMS)

@app.route("/api/calc", methods=["POST"])
def calc():
    d = request.get_json(force=True)
    lat = float(d["lat"])
    lon = float(d["lon"])
    sat = SATELLITES[d["satellite"]]
    az, el, skew = look_angles(lat, lon, sat["lon"])
    system = d.get("system", "single")
    receivers = max(1, int(d.get("receivers", 1)))
    dish = sat["dish"]
    if d.get("multifeed"):
        dish = max(dish + 15, 80)
    if receivers > 8 and system in ("single", "twin", "quad", "octo"):
        advice = "Per questo numero di utenze è consigliato un sistema multiswitch, Wideband o dCSS."
    else:
        advice = "Configurazione coerente con il numero di utenze indicato."
    return jsonify({
        "satellite": sat["name"],
        "azimuth": az,
        "elevation": el,
        "skew": skew,
        "dish_min_cm": dish,
        "transponder": sat["tp"],
        "tp_note": sat["note"],
        "system": SYSTEMS[system],
        "advice": advice
    })

app.run(host="0.0.0.0", port=8099)
