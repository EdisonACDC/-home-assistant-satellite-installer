from flask import Flask, render_template, request, jsonify
from math import radians, degrees, atan2, cos, sin, sqrt, atan
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

app = Flask(__name__)

SATELLITES = {
    "astra19": {"name":"Astra 19.2°E","lon":19.2,"dish":60,"tp":"11347 V 22000","freq":11347,"pol":"V","sr":22000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["3sat HD","KiKA HD","ZDFinfo HD"],"note":"Transponder ZDF Vision."},
    "hotbird13": {"name":"Hotbird 13.0°E","lon":13.0,"dish":60,"tp":"10719 V 27500","freq":10719,"pol":"V","sr":27500,"fec":"5/6","system":"DVB-S2 8PSK","channels":["TVP Info HD"],"note":"Transponder di riferimento."},
    "eutelsat16": {"name":"Eutelsat 16A 16.0°E","lon":16.0,"dish":80,"tp":"11283 V 30000","freq":11283,"pol":"V","sr":30000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["FilmBox+ Hits Adria HD","Dizi HD"],"note":"Riferimento area balcanica."},
    "astra28": {"name":"Astra 28.2°E","lon":28.2,"dish":80,"tp":"11023 H 23000","freq":11023,"pol":"H","sr":23000,"fec":"3/4","system":"DVB-S2 8PSK","channels":["BBC One Scotland HD","BBC One Wales HD","BBC News UK"],"note":"Beam UK."},
    "turksat42": {"name":"Türksat 42.0°E","lon":42.0,"dish":80,"tp":"12380 V 27500","freq":12380,"pol":"V","sr":27500,"fec":"3/4","system":"DVB-S","channels":["TGRT Haber"],"note":"Beam West."},
    "thor08w": {"name":"Thor 0.8°W","lon":-0.8,"dish":80,"tp":"11823 H 30000","freq":11823,"pol":"H","sr":30000,"fec":"5/6","system":"DVB-S2 8PSK","channels":["TV 2 Hungary HD","M1 Hungary HD","Digi Sport 1 HD","Digi Sport 2 HD","Pro TV HD","TVR Info","TVR Cultural"],"note":"Digi România; molti servizi criptati."},
    "eutelsat5w": {"name":"Eutelsat 5 West B 5.0°W","lon":-5.0,"dish":80,"tp":"11096 V 29950","freq":11096,"pol":"V","sr":29950,"fec":"3/4","system":"DVB-S2 8PSK","channels":["TF1 HD","M6 HD","ARTE Français HD","6ter HD","KTO"],"note":"Fransat; molti servizi criptati."}
}

SYSTEMS = {"auto":"Automatico (consigliato)","single":"LNB universale Single","twin":"LNB universale Twin","quad":"LNB universale Quad","octo":"LNB universale Octo","unicable":"SCR / Unicable EN50494","jess":"JESS / dCSS EN50607","quattro":"LNB Quattro + multiswitch","wideband":"LNB Wideband + multiswitch"}

WIDEBAND_LNBS = {
    "generic10410":{"name":"Wideband generico LO 10.41 GHz","brand":"Generico","lo":10410,"if_min":290,"if_max":2340,"outputs":"H + V"},
    "inverto10400":{"name":"Inverto Wideband EU LO 10.40 GHz","brand":"Inverto","lo":10400,"if_min":300,"if_max":2350,"outputs":"H + V"},
    "inverto10410":{"name":"Inverto Wideband LO 10.41 GHz","brand":"Inverto","lo":10410,"if_min":290,"if_max":2340,"outputs":"H + V"},
    "johansson9720":{"name":"Johansson 9720 Wideband","brand":"Johansson","lo":10410,"if_min":290,"if_max":2340,"outputs":"H + V"},
    "triax_twb205":{"name":"TRIAX TWB 205 Wideband","brand":"TRIAX","lo":10410,"if_min":290,"if_max":2340,"outputs":"H + V"},
    "televes747402":{"name":"Televes 747402 WideBand","brand":"Televes","lo":10410,"if_min":290,"if_max":2340,"outputs":"H + V"}
}

def look_angles(lat,lon,sat_lon):
    phi=radians(lat); dl=radians(sat_lon-lon); c=cos(phi)*cos(dl)
    elevation=degrees(atan((c-0.1512)/sqrt(max(1e-12,1-c*c))))
    az=degrees(atan2(sin(dl),-sin(phi)*cos(dl)))
    return round((180+az)%360,1),round(elevation,1),round(degrees(atan2(sin(dl),sin(phi))),1)

def recommend_system(receivers,sat_count):
    if sat_count>2 or receivers>8:return "quattro"
    if receivers<=1 and sat_count==1:return "single"
    if receivers<=2 and sat_count==1:return "twin"
    if receivers<=4 and sat_count==1:return "quad"
    if receivers<=8 and sat_count==1:return "octo"
    return "quattro"

def build_layout(system,receivers,sat_count):
    c=[]; w=[]
    if system=="single": c.append(f"{sat_count} × LNB Single"); w.append("1 cavo per satellite")
    elif system=="twin": c.append(f"{sat_count} × LNB Twin"); w.append("2 uscite indipendenti per LNB")
    elif system=="quad": c.append(f"{sat_count} × LNB Quad"); w.append("Fino a 4 linee indipendenti per LNB")
    elif system=="octo": c.append(f"{sat_count} × LNB Octo"); w.append("Fino a 8 linee indipendenti per LNB")
    elif system=="quattro": c += [f"{sat_count} × LNB Quattro",f"1 × multiswitch ≥ {sat_count*4} ingressi SAT / {receivers} uscite"]; w += [f"{sat_count*4} cavi VL/VH/HL/HH",f"{receivers} linee multiswitch→tuner"]
    elif system=="wideband": c += [f"{sat_count} × LNB Wideband",f"1 × multiswitch Wideband/dCSS ≥ {sat_count*2} ingressi SAT"]; w.append(f"{sat_count*2} cavi: H + V per satellite")
    elif system in ("unicable","jess"): c.append(f"{sat_count} × sorgente compatibile {SYSTEMS[system]}"); w.append("Distribuzione su singolo cavo con User Band")
    if sat_count>1 and system in ("single","twin","quad","octo"): c.append("Commutatore DiSEqC"); w.append("LNB → DiSEqC → tuner")
    return c,w

def meter_settings(sat,system,diseqc_port=1,wideband_key="generic10410"):
    freq=sat["freq"]; pol=sat["pol"]; high=freq>=11700; voltage="18 V" if pol=="H" else "13 V"
    settings={"meter":"Amiko X-Finder 3","lnb_type":"Universal (9750/10600)","frequency_mhz":freq,"polarization":pol,"symbol_rate":sat["sr"],"fec":sat["fec"],"dvb":sat["system"],"lnb_voltage":voltage,"tone_22khz":"AUTO (Universal)","band":"Alta" if high else "Bassa","lof":"9750 / 10600 MHz","if_mhz":freq-(10600 if high else 9750),"diseqc":"Disable" if diseqc_port==1 else f"DiSEqC 1.0: {diseqc_port}/4","scr":"OFF","supported":True,"warning":"","steps":[]}
    if system=="unicable": settings.update({"lnb_type":"Unicable","scr":"Seleziona la User Band assegnata","tone_22khz":"Gestito da Unicable"})
    elif system=="jess": settings.update({"lnb_type":"Unicable","scr":"X-Finder 3 non mostra JESS come voce separata","warning":"Verifica compatibilità firmware/UB con EN50607."})
    elif system=="quattro": settings["warning"]="Collegati direttamente alla corretta uscita VL/VH/HL/HH del Quattro."
    elif system=="wideband":
        wb=WIDEBAND_LNBS.get(wideband_key,WIDEBAND_LNBS["generic10410"]); ifreq=abs(freq-wb["lo"]); within=950<=ifreq<=2150
        settings.update({"lnb_type":f"USER → LO {wb['lo']} MHz","tone_22khz":"OFF","band":"Wideband singola polarizzazione","lof":f"{wb['lo']} MHz","if_mhz":ifreq,"scr":"OFF","wideband_model":wb["name"],"wideband_output":pol,"supported":within,"warning":f"Collega lo X-Finder 3 direttamente all'uscita {pol} del LNB. IF calcolata {ifreq} MHz. " + ("È dentro il range 950–2150 MHz dello strumento." if within else "È FUORI dal range 950–2150 MHz dello X-Finder 3: scegli un altro transponder oppure misura a valle del multiswitch.")})
    settings["steps"]=[f"MENU → Installazione/Satellite → {sat['name']}",f"LNB Type: {settings['lnb_type']}",f"TP: {freq} MHz {pol} SR {sat['sr']}",f"LNB Power: {settings['lnb_voltage']}",f"22K: {settings['tone_22khz']}",f"DiSEqC 1.0: {settings['diseqc']}","Apri la misura e cerca LOCK; poi massimizza qualità/MER e controlla BER."]
    return settings

@app.route("/")
def index(): return render_template("index.html",satellites=SATELLITES,systems=SYSTEMS,wideband_lnbs=WIDEBAND_LNBS)

@app.route("/api/geocode",methods=["POST"])
def geocode():
    d=request.get_json(force=True); city=(d.get("city") or "").strip()
    if not city:return jsonify({"error":"Inserisci il nome della città"}),400
    try:
        params=urlencode({"q":city,"format":"jsonv2","limit":5,"addressdetails":1}); req=Request("https://nominatim.openstreetmap.org/search?"+params,headers={"User-Agent":"SatelliteInstallerPro/0.4.2"})
        with urlopen(req,timeout=8) as r:data=json.loads(r.read().decode("utf-8"))
        return jsonify({"results":[{"name":x.get("display_name",city),"lat":float(x["lat"]),"lon":float(x["lon"])} for x in data[:5]]})
    except Exception as e:return jsonify({"error":"Ricerca città non disponibile.","detail":str(e)}),502

@app.route("/api/calc",methods=["POST"])
def calc():
    d=request.get_json(force=True); lat=float(d["lat"]); lon=float(d["lon"]); satellite_ids=[s for s in (d.get("satellites") or ["astra19"]) if s in SATELLITES] or ["astra19"]
    receivers=max(1,int(d.get("receivers",1))); system=d.get("system","auto"); system=recommend_system(receivers,len(satellite_ids)) if system=="auto" else system; wb_key=d.get("wideband_lnb","generic10410")
    results=[]; dish=0; sat_lons=[]
    for idx,sid in enumerate(satellite_ids,1):
        sat=SATELLITES[sid]; az,el,skew=look_angles(lat,lon,sat["lon"]); dish=max(dish,sat["dish"]); sat_lons.append(sat["lon"])
        results.append({"id":sid,"satellite":sat["name"],"azimuth":az,"elevation":el,"skew":skew,"transponder":sat["tp"],"fec":sat["fec"],"dvb_system":sat["system"],"channels":sat["channels"],"tp_note":sat["note"],"meter":meter_settings(sat,system,idx,wb_key)})
    if len(satellite_ids)>1:
        spread=max(sat_lons)-min(sat_lons); dish=max(dish+15,80)+(10 if spread>12 else 0)
    components,wiring=build_layout(system,receivers,len(satellite_ids)); warnings=[]
    if len(satellite_ids)>4:warnings.append("Per più di 4 satelliti valuta multiswitch in cascata o DiSEqC avanzato.")
    if any(x["elevation"]<=0 for x in results):warnings.append("Almeno un satellite risulta sotto l'orizzonte.")
    if system=="wideband":warnings.append("Wideband: lo X-Finder 3 va impostato in USER con la LO reale del modello; verifica sempre che la IF cada tra 950 e 2150 MHz.")
    return jsonify({"location":{"lat":lat,"lon":lon},"satellites":results,"dish_min_cm":dish,"system_key":system,"system":SYSTEMS[system],"components":components,"wiring":wiring,"warnings":warnings})

app.run(host="0.0.0.0",port=8099)
