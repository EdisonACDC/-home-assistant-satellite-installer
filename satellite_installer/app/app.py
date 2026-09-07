from flask import Flask, render_template, request, jsonify
from math import radians, degrees, atan2, cos, sin, sqrt, atan
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

app = Flask(__name__)

SATELLITES = {
    "astra19": {"name":"Astra 19.2°E","lon":19.2,"dish":60,"tp":"11347 V 22000","freq":11347,"pol":"V","sr":22000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["3sat HD","KiKA HD","ZDFinfo HD"],"note":"Transponder ZDF Vision, ottimo come riferimento in Europa centrale."},
    "hotbird13": {"name":"Hotbird 13.0°E","lon":13.0,"dish":60,"tp":"10719 V 27500","freq":10719,"pol":"V","sr":27500,"fec":"5/6","system":"DVB-S2 8PSK","channels":["TVP Info HD"],"note":"Transponder di riferimento; la composizione può cambiare."},
    "eutelsat16": {"name":"Eutelsat 16A 16.0°E","lon":16.0,"dish":80,"tp":"11283 V 30000","freq":11283,"pol":"V","sr":30000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["FilmBox+ Hits Adria HD","Dizi HD"],"note":"Riferimento utile per impianti dell'area balcanica."},
    "astra28": {"name":"Astra 28.2°E","lon":28.2,"dish":80,"tp":"11023 H 23000","freq":11023,"pol":"H","sr":23000,"fec":"3/4","system":"DVB-S2 8PSK","channels":["BBC One Scotland HD","BBC One Wales HD","BBC News UK"],"note":"Beam UK: in Europa continentale può richiedere una parabola più grande."},
    "turksat42": {"name":"Türksat 42.0°E","lon":42.0,"dish":80,"tp":"12380 V 27500","freq":12380,"pol":"V","sr":27500,"fec":"3/4","system":"DVB-S","channels":["TGRT Haber"],"note":"Transponder sul beam West."},
    "thor08w": {"name":"Thor 0.8°W","lon":-0.8,"dish":80,"tp":"11823 H 30000","freq":11823,"pol":"H","sr":30000,"fec":"5/6","system":"DVB-S2 8PSK","channels":["TV 2 Hungary HD","M1 Hungary HD","Digi Sport 1 HD","Digi Sport 2 HD","Pro TV HD","TVR Info","TVR Cultural"],"note":"Transponder Digi România; molti servizi sono criptati."},
    "eutelsat5w": {"name":"Eutelsat 5 West B 5.0°W","lon":-5.0,"dish":80,"tp":"11096 V 29950","freq":11096,"pol":"V","sr":29950,"fec":"3/4","system":"DVB-S2 8PSK","channels":["TF1 HD","M6 HD","ARTE Français HD","6ter HD","KTO"],"note":"Transponder Fransat; molti canali sono criptati Viaccess."}
}

SYSTEMS = {"auto":"Automatico (consigliato)","single":"LNB universale Single","twin":"LNB universale Twin","quad":"LNB universale Quad","octo":"LNB universale Octo","unicable":"SCR / Unicable EN50494","jess":"JESS / dCSS EN50607","quattro":"LNB Quattro + multiswitch","wideband":"LNB Wideband + multiswitch"}

def look_angles(lat, lon, sat_lon):
    phi=radians(lat); dl=radians(sat_lon-lon); c=cos(phi)*cos(dl)
    elevation=degrees(atan((c-0.1512)/sqrt(max(1e-12,1-c*c))))
    az=degrees(atan2(sin(dl),-sin(phi)*cos(dl))); azimuth=(180+az)%360
    skew=degrees(atan2(sin(dl),sin(phi)))
    return round(azimuth,1),round(elevation,1),round(skew,1)

def recommend_system(receivers,sat_count):
    if sat_count>2 or receivers>8:return "quattro"
    if receivers<=1 and sat_count==1:return "single"
    if receivers<=2 and sat_count==1:return "twin"
    if receivers<=4 and sat_count==1:return "quad"
    if receivers<=8 and sat_count==1:return "octo"
    return "quattro"

def build_layout(system,receivers,sat_count):
    components=[]; wiring=[]
    if system=="single": components.append(f"{sat_count} × LNB Single"); wiring.append("1 cavo coassiale per satellite verso ricevitore/DiSEqC")
    elif system=="twin": components.append(f"{sat_count} × LNB Twin"); wiring.append("2 uscite indipendenti per ogni LNB")
    elif system=="quad": components.append(f"{sat_count} × LNB Quad"); wiring.append("Fino a 4 linee indipendenti per ogni LNB")
    elif system=="octo": components.append(f"{sat_count} × LNB Octo"); wiring.append("Fino a 8 linee indipendenti per ogni LNB")
    elif system=="quattro": components += [f"{sat_count} × LNB Quattro",f"1 × multiswitch con almeno {sat_count*4} ingressi SAT e {receivers} uscite"]; wiring += [f"{sat_count*4} cavi LNB→multiswitch: VL / VH / HL / HH per satellite",f"{receivers} linee indipendenti multiswitch→tuner"]
    elif system=="wideband": components += [f"{sat_count} × LNB Wideband",f"1 × multiswitch Wideband/dCSS con almeno {sat_count*2} ingressi SAT"]; wiring.append(f"{sat_count*2} cavi LNB→multiswitch: H + V per satellite")
    elif system in ("unicable","jess"): components.append(f"{sat_count} × sorgente compatibile {SYSTEMS[system]}"); wiring.append("Distribuzione su singolo cavo con user band separate")
    if sat_count>1 and system in ("single","twin","quad","octo"): components.append("Commutatore DiSEqC adeguato"); wiring.append("Ogni LNB a un ingresso DiSEqC, uscita verso tuner")
    return components,wiring

def meter_settings(sat, system, diseqc_port=1):
    freq=sat["freq"]; pol=sat["pol"]; high=freq>=11700
    voltage="18 V" if pol=="H" else "13 V"
    tone="AUTO (gestito da Universal)" if True else ("ON" if high else "OFF")
    ifreq=freq-(10600 if high else 9750)
    settings={
        "meter":"Amiko X-Finder 3",
        "lnb_type":"Universal (9750-10600)",
        "frequency_mhz":freq,"polarization":pol,"symbol_rate":sat["sr"],"fec":sat["fec"],"dvb":sat["system"],
        "lnb_voltage":voltage,"tone_22khz":tone,"band":"Alta" if high else "Bassa","lof":"9750 / 10600 MHz","if_mhz":ifreq,
        "diseqc":"Disable" if diseqc_port==1 else f"DiSEqC 1.0: {diseqc_port}/4",
        "scr":"OFF","supported":True,"warning":"","steps":[]
    }
    if system=="unicable":
        settings["lnb_type"]="Unicable"; settings["scr"]="Unicable: selezionare la User Band assegnata"; settings["tone_22khz"]="Gestito dal modo Unicable"
    elif system=="jess":
        settings["lnb_type"]="Unicable (solo se compatibile con il profilo/UB del tuo impianto)"; settings["scr"]="Il manuale X-Finder 3 documenta Unicable; EN50607/JESS non è indicato come voce separata"; settings["warning"]="Per dCSS/JESS verifica che la User Band e il comando siano compatibili con il firmware del tuo X-Finder 3."
    elif system=="quattro":
        settings["lnb_type"]="Universal / Standard / User secondo il punto di misura"; settings["warning"]="Su LNB Quattro misura la singola uscita VL/VH/HL/HH coerente con polarizzazione e banda; non usare una voce 'Quattro' se non presente nel menu."
    elif system=="wideband":
        settings["lnb_type"]="NON disponibile come profilo Wideband nello X-Finder 3"; settings["supported"]=False; settings["warning"]="Lo X-Finder 3 non documenta un tipo LNB Wideband. Per impianti Wideband misura preferibilmente a valle di un multiswitch su un'uscita legacy/universale compatibile. Non impostare un profilo Wideband inesistente."
        settings["tone_22khz"]="N/D per misura diretta Wideband"; settings["lnb_voltage"]="Secondo uscita/multiswitch"; settings["if_mhz"]="N/D"
    settings["steps"]=[f"MENU → Installazione / Satellite → seleziona {sat['name']}",f"LNB Type: {settings['lnb_type']}",f"TP Index: imposta o crea {freq} MHz, {pol}, SR {sat['sr']}",f"LNB Power: {settings['lnb_voltage']}",f"22K: {settings['tone_22khz']}",f"DiSEqC 1.0: {settings['diseqc']}","Apri la misura del TP e verifica LOCK, livello, qualità/MER e BER."]
    return settings

@app.route("/")
def index(): return render_template("index.html",satellites=SATELLITES,systems=SYSTEMS)

@app.route("/api/geocode",methods=["POST"])
def geocode():
    d=request.get_json(force=True); city=(d.get("city") or "").strip()
    if not city:return jsonify({"error":"Inserisci il nome della città"}),400
    try:
        params=urlencode({"q":city,"format":"jsonv2","limit":5,"addressdetails":1}); req=Request("https://nominatim.openstreetmap.org/search?"+params,headers={"User-Agent":"SatelliteInstallerPro/0.4.1 (Home Assistant add-on)"})
        with urlopen(req,timeout=8) as r:data=json.loads(r.read().decode("utf-8"))
        return jsonify({"results":[{"name":x.get("display_name",city),"lat":float(x["lat"]),"lon":float(x["lon"])} for x in data[:5]]})
    except Exception as e:return jsonify({"error":"Ricerca città non disponibile. Puoi inserire manualmente latitudine e longitudine.","detail":str(e)}),502

@app.route("/api/calc",methods=["POST"])
def calc():
    d=request.get_json(force=True); lat=float(d["lat"]); lon=float(d["lon"]); satellite_ids=d.get("satellites") or [d.get("satellite","astra19")]; satellite_ids=[s for s in satellite_ids if s in SATELLITES] or ["astra19"]
    receivers=max(1,int(d.get("receivers",1))); system=d.get("system","auto"); system=recommend_system(receivers,len(satellite_ids)) if system=="auto" else system
    results=[]; dish=0; sat_lons=[]
    for idx,sid in enumerate(satellite_ids,1):
        sat=SATELLITES[sid]; az,el,skew=look_angles(lat,lon,sat["lon"]); dish=max(dish,sat["dish"]); sat_lons.append(sat["lon"])
        results.append({"id":sid,"satellite":sat["name"],"azimuth":az,"elevation":el,"skew":skew,"transponder":sat["tp"],"fec":sat["fec"],"dvb_system":sat["system"],"channels":sat["channels"],"tp_note":sat["note"],"meter":meter_settings(sat,system,idx)})
    if len(satellite_ids)>1:
        spread=max(sat_lons)-min(sat_lons); dish=max(dish+15,80); dish += 10 if spread>12 else 0
    components,wiring=build_layout(system,receivers,len(satellite_ids)); warnings=[]
    if len(satellite_ids)>4:warnings.append("Per più di 4 satelliti valuta multiswitch in cascata o DiSEqC avanzato.")
    if any(x["elevation"]<=0 for x in results):warnings.append("Almeno un satellite risulta sotto l'orizzonte.")
    if receivers>8 and system in ("single","twin","quad","octo"):warnings.append("Con più di 8 tuner è consigliato Quattro/Wideband o dCSS.")
    if system=="wideband":warnings.append("Amiko X-Finder 3: nessun profilo LNB Wideband documentato. Misura consigliata a valle del multiswitch su uscita legacy compatibile.")
    return jsonify({"location":{"lat":lat,"lon":lon},"satellites":results,"dish_min_cm":dish,"system_key":system,"system":SYSTEMS[system],"components":components,"wiring":wiring,"warnings":warnings})

app.run(host="0.0.0.0",port=8099)
