from flask import Flask, render_template, request, jsonify
from math import radians, degrees, atan2, cos, sin, sqrt, atan, ceil

app = Flask(__name__)

SATELLITES = {
    "astra19": {"name": "Astra 19.2°E", "lon": 19.2, "dish": 60, "tp": "11347 V 22000", "note": "Transponder di riferimento: verificare sempre sullo strumento prima del puntamento definitivo."},
    "hotbird13": {"name": "Hotbird 13.0°E", "lon": 13.0, "dish": 60, "tp": "10719 V 27500", "note": "Transponder di riferimento: verificare sempre sullo strumento prima del puntamento definitivo."},
    "thor08w": {"name": "Thor 0.8°W", "lon": -0.8, "dish": 80, "tp": "11823 H 30000", "note": "Riferimento utile per Digi/Thor; confermare il transponder attivo sul misuratore."},
    "eutelsat5w": {"name": "Eutelsat 5°W", "lon": -5.0, "dish": 80, "tp": "11096 V 29950", "note": "Riferimento iniziale; verificare il transponder attivo prima del collaudo."},
}

SYSTEMS = {
    "auto": "Scelta automatica professionale",
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

def auto_system(tuners, sat_count):
    if sat_count == 1:
        if tuners <= 1: return "single"
        if tuners <= 2: return "twin"
        if tuners <= 4: return "quad"
        if tuners <= 8: return "octo"
        return "jess"
    if tuners <= 4 and sat_count <= 4:
        return "quad"
    return "quattro"

def design_system(system, tuners, satellites):
    sat_count = len(satellites)
    if system == "auto":
        system = auto_system(tuners, sat_count)

    components = []
    cabling = []
    warnings = []
    outputs = {"single":1, "twin":2, "quad":4, "octo":8}

    if system in outputs:
        cap = outputs[system]
        components.append(f"{sat_count} × {SYSTEMS[system]}")
        if sat_count == 1:
            cabling.append(f"{min(tuners, cap)} cavo/i coassiale/i diretto/i dall'LNB ai tuner")
            if tuners > cap:
                warnings.append(f"Questo LNB ha solo {cap} uscita/e indipendente/i: servono più uscite o un sistema multiswitch/dCSS.")
        else:
            components.append(f"Commutazione DiSEqC per {sat_count} satelliti su ogni linea tuner")
            cabling.append(f"Per ogni tuner: {sat_count} cavi dagli LNB al relativo commutatore DiSEqC, poi 1 cavo al tuner")
            if tuners > cap:
                warnings.append(f"Con {SYSTEMS[system]} puoi servire al massimo {cap} tuner indipendenti per satellite.")
    elif system == "unicable":
        components += [f"{sat_count} × LNB/Sistema SCR EN50494 compatibile", "Splitter SAT DC-pass compatibili Unicable"]
        cabling.append("1 dorsale coassiale Unicable, derivata con splitter compatibili verso i ricevitori")
        warnings.append("Verificare il numero di User Band disponibili e assegnare una frequenza UB diversa a ogni tuner.")
        if sat_count > 2:
            warnings.append("Per più satelliti, verificare esplicitamente compatibilità SCR + commutazione satelliti del multiswitch/ricevitore.")
    elif system == "jess":
        components += [f"Sistema dCSS/JESS EN50607 per {sat_count} satellite/i", "Splitter SAT DC-pass 5–2400 MHz compatibili dCSS"]
        cabling.append("1 dorsale coassiale principale; più tuner condividono il cavo usando User Band separate")
        warnings.append("Configurare EN50607 e User Band/frequenze secondo il modello reale del multiswitch/LNB.")
    elif system == "quattro":
        inputs = sat_count * 4
        ms_out = max(4, int(ceil(tuners / 4.0) * 4))
        components += [f"{sat_count} × LNB Quattro", f"Multiswitch almeno {inputs} ingressi SAT (+ terrestre se necessario) e {ms_out} uscite"]
        cabling.append(f"4 cavi per satellite LNB→multiswitch: VL, VH, HL, HH ({inputs} cavi SAT totali in ingresso)")
        cabling.append(f"1 cavo indipendente dal multiswitch a ciascun tuner/utenza ({tuners} linea/e)")
    elif system == "wideband":
        inputs = sat_count * 2
        components += [f"{sat_count} × LNB Wideband", f"Multiswitch Wideband/dCSS con almeno {inputs} ingressi Wideband"]
        cabling.append(f"2 cavi per satellite LNB→multiswitch: V e H ({inputs} cavi SAT totali in ingresso)")
        cabling.append("Dal multiswitch: uscite legacy oppure dCSS/Unicable in base ai ricevitori")
        warnings.append("Wideband non è compatibile con un normale multiswitch Quattro: il multiswitch deve dichiarare ingressi Wideband.")

    return system, components, cabling, warnings

@app.route("/")
def index():
    return render_template("index.html", satellites=SATELLITES, systems=SYSTEMS)

@app.route("/api/calc", methods=["POST"])
def calc():
    d = request.get_json(force=True)
    lat = float(d["lat"])
    lon = float(d["lon"])
    sat_keys = d.get("satellites") or [d.get("satellite", "astra19")]
    sat_keys = [k for k in sat_keys if k in SATELLITES]
    if not sat_keys:
        return jsonify({"error": "Seleziona almeno un satellite"}), 400

    tuners = max(1, int(d.get("receivers", 1)))
    requested_system = d.get("system", "auto")
    sats = [SATELLITES[k] for k in sat_keys]
    primary = sats[0]
    az, el, skew = look_angles(lat, lon, primary["lon"])

    max_dish = max(s["dish"] for s in sats)
    orbital_span = max(s["lon"] for s in sats) - min(s["lon"] for s in sats)
    dish = max_dish
    if len(sats) > 1:
        dish = max(80, max_dish + 10)
        if orbital_span > 10: dish = max(dish, 90)
        if orbital_span > 20: dish = max(dish, 100)

    system, components, cabling, warnings = design_system(requested_system, tuners, sats)
    angles = []
    for s in sats:
        a, e, sk = look_angles(lat, lon, s["lon"])
        angles.append({"satellite": s["name"], "azimuth": a, "elevation": e, "skew": sk, "transponder": s["tp"]})

    multifeed_note = None
    if len(sats) > 1:
        west = min(sats, key=lambda x: x["lon"])["name"]
        east = max(sats, key=lambda x: x["lon"])["name"]
        multifeed_note = f"Escursione orbitale {orbital_span:.1f}°. La posizione fisica destra/sinistra degli LNB dipende dalla vista frontale o da dietro la parabola: usare i valori di puntamento e rifinire ogni fuoco con il misuratore. Satelliti estremi: {west} ↔ {east}."

    return jsonify({
        "version": "0.2.0",
        "primary_satellite": primary["name"],
        "azimuth": az, "elevation": el, "skew": skew,
        "dish_min_cm": dish,
        "system_key": system,
        "system": SYSTEMS[system],
        "tuners": tuners,
        "satellite_count": len(sats),
        "angles": angles,
        "components": components,
        "cabling": cabling,
        "warnings": warnings,
        "multifeed_note": multifeed_note
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)
