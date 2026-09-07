from flask import Flask, render_template, request, jsonify
from math import radians, degrees, atan2, cos, sin, sqrt, atan
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

app = Flask(__name__)

SATELLITES = {
    "astra19": {
        "name": "Astra 19.2°E", "lon": 19.2, "dish": 60,
        "tp": "11347 V 22000", "fec": "2/3", "system": "DVB-S2 8PSK",
        "channels": ["3sat HD", "KiKA HD", "ZDFinfo HD"],
        "note": "Transponder ZDF Vision, ottimo come riferimento in Europa centrale."
    },
    "hotbird13": {
        "name": "Hotbird 13.0°E", "lon": 13.0, "dish": 60,
        "tp": "10719 V 27500", "fec": "5/6", "system": "DVB-S2 8PSK",
        "channels": ["TVP Info HD"],
        "note": "Transponder Canal+ Polska. La composizione può cambiare nel tempo."
    },
    "eutelsat16": {
        "name": "Eutelsat 16A 16.0°E", "lon": 16.0, "dish": 80,
        "tp": "11283 V 30000", "fec": "2/3", "system": "DVB-S2 8PSK",
        "channels": ["FilmBox+ Hits Adria HD", "Dizi HD"],
        "note": "Riferimento utile per impianti dell'area balcanica."
    },
    "astra28": {
        "name": "Astra 28.2°E", "lon": 28.2, "dish": 80,
        "tp": "11023 H 23000", "fec": "3/4", "system": "DVB-S2 8PSK",
        "channels": ["BBC One Scotland HD", "BBC One Wales HD", "BBC News UK"],
        "note": "Beam UK: in Europa continentale può richiedere una parabola molto più grande."
    },
    "turksat42": {
        "name": "Türksat 42.0°E", "lon": 42.0, "dish": 80,
        "tp": "12380 V 27500", "fec": "3/4", "system": "DVB-S",
        "channels": ["TGRT Haber"],
        "note": "Transponder sul beam West."
    },
    "thor08w": {
        "name": "Thor 0.8°W", "lon": -0.8, "dish": 80,
        "tp": "11823 H 30000", "fec": "5/6", "system": "DVB-S2 8PSK",
        "channels": ["TV 2 Hungary HD", "M1 Hungary HD", "Digi Sport 1 HD", "Digi Sport 2 HD", "Pro TV HD", "TVR Info", "TVR Cultural"],
        "note": "Transponder Digi România. Molti servizi sono criptati e richiedono abbonamento."
    },
    "eutelsat5w": {
        "name": "Eutelsat 5 West B 5.0°W", "lon": -5.0, "dish": 80,
        "tp": "11096 V 29950", "fec": "3/4", "system": "DVB-S2 8PSK",
        "channels": ["TF1 HD", "M6 HD", "ARTE Français HD", "6ter HD", "KTO"],
        "note": "Transponder Fransat; molti canali sono criptati Viaccess."
    }
}

SYSTEMS = {
    "auto": "Automatico (consigliato)",
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

def recommend_system(receivers, sat_count):
    if sat_count > 2 or receivers > 8:
        return "quattro"
    if receivers <= 1 and sat_count == 1:
        return "single"
    if receivers <= 2 and sat_count == 1:
        return "twin"
    if receivers <= 4 and sat_count == 1:
        return "quad"
    if receivers <= 8 and sat_count == 1:
        return "octo"
    return "quattro"

def build_layout(system, receivers, sat_count):
    components = []
    wiring = []
    if system == "single":
        components.append(f"{sat_count} × LNB Single")
        wiring.append("1 cavo coassiale per satellite verso il ricevitore/DiSEqC")
    elif system == "twin":
        components.append(f"{sat_count} × LNB Twin")
        wiring.append("2 uscite indipendenti per ogni LNB")
    elif system == "quad":
        components.append(f"{sat_count} × LNB Quad")
        wiring.append("Fino a 4 linee indipendenti per ogni LNB")
    elif system == "octo":
        components.append(f"{sat_count} × LNB Octo")
        wiring.append("Fino a 8 linee indipendenti per ogni LNB")
    elif system == "quattro":
        components.append(f"{sat_count} × LNB Quattro")
        components.append(f"1 × multiswitch con almeno {sat_count * 4} ingressi SAT e {receivers} uscite")
        wiring.append(f"{sat_count * 4} cavi LNB→multiswitch: VL / VH / HL / HH per ciascun satellite")
        wiring.append(f"{receivers} linee indipendenti multiswitch→tuner")
    elif system == "wideband":
        components.append(f"{sat_count} × LNB Wideband")
        components.append(f"1 × multiswitch Wideband/dCSS compatibile con almeno {sat_count * 2} ingressi SAT")
        wiring.append(f"{sat_count * 2} cavi LNB→multiswitch: H + V per ciascun satellite")
    elif system in ("unicable", "jess"):
        components.append(f"{sat_count} × sorgente compatibile {SYSTEMS[system]}")
        wiring.append("Distribuzione su singolo cavo con user band separate per tuner")
    if sat_count > 1 and system in ("single", "twin", "quad", "octo"):
        components.append("Commutatore DiSEqC adeguato al numero di satelliti")
        wiring.append("Collegare ogni LNB a un ingresso DiSEqC e l'uscita al tuner")
    return components, wiring

@app.route("/")
def index():
    return render_template("index.html", satellites=SATELLITES, systems=SYSTEMS)

@app.route("/api/geocode", methods=["POST"])
def geocode():
    d = request.get_json(force=True)
    city = (d.get("city") or "").strip()
    if not city:
        return jsonify({"error": "Inserisci il nome della città"}), 400
    try:
        params = urlencode({"q": city, "format": "jsonv2", "limit": 5, "addressdetails": 1})
        req = Request(
            "https://nominatim.openstreetmap.org/search?" + params,
            headers={"User-Agent": "SatelliteInstallerPro/0.3.0 (Home Assistant add-on)"}
        )
        with urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        results = [{"name": x.get("display_name", city), "lat": float(x["lat"]), "lon": float(x["lon"])} for x in data[:5]]
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": "Ricerca città non disponibile. Puoi inserire manualmente latitudine e longitudine.", "detail": str(e)}), 502

@app.route("/api/calc", methods=["POST"])
def calc():
    d = request.get_json(force=True)
    lat = float(d["lat"])
    lon = float(d["lon"])
    satellite_ids = d.get("satellites") or [d.get("satellite", "astra19")]
    satellite_ids = [s for s in satellite_ids if s in SATELLITES]
    if not satellite_ids:
        satellite_ids = ["astra19"]
    receivers = max(1, int(d.get("receivers", 1)))
    system = d.get("system", "auto")
    if system == "auto":
        system = recommend_system(receivers, len(satellite_ids))

    results = []
    dish = 0
    sat_lons = []
    for sid in satellite_ids:
        sat = SATELLITES[sid]
        az, el, skew = look_angles(lat, lon, sat["lon"])
        dish = max(dish, sat["dish"])
        sat_lons.append(sat["lon"])
        results.append({
            "id": sid,
            "satellite": sat["name"],
            "azimuth": az,
            "elevation": el,
            "skew": skew,
            "transponder": sat["tp"],
            "fec": sat["fec"],
            "dvb_system": sat["system"],
            "channels": sat["channels"],
            "tp_note": sat["note"]
        })

    if len(satellite_ids) > 1:
        spread = max(sat_lons) - min(sat_lons)
        dish = max(dish + 15, 80)
        if spread > 12:
            dish += 10

    components, wiring = build_layout(system, receivers, len(satellite_ids))
    warnings = []
    if len(satellite_ids) > 4:
        warnings.append("Per più di 4 satelliti valuta multiswitch in cascata o commutazione DiSEqC avanzata.")
    if any(x["elevation"] <= 0 for x in results):
        warnings.append("Almeno un satellite risulta sotto l'orizzonte dalla località selezionata.")
    if receivers > 8 and system in ("single", "twin", "quad", "octo"):
        warnings.append("Con più di 8 tuner è consigliato passare a multiswitch Quattro/Wideband o dCSS.")

    return jsonify({
        "location": {"lat": lat, "lon": lon},
        "satellites": results,
        "dish_min_cm": dish,
        "system_key": system,
        "system": SYSTEMS[system],
        "components": components,
        "wiring": wiring,
        "warnings": warnings
    })

app.run(host="0.0.0.0", port=8099)
