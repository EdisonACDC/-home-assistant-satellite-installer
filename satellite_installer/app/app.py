from flask import Flask, render_template, request, jsonify
from math import radians, degrees, atan2, cos, sin, sqrt, atan
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

app = Flask(__name__)

SATELLITES = {
    "astra19":{"name":"Astra 19.2°E","lon":19.2,"dish":60},
    "hotbird13":{"name":"Hotbird 13.0°E","lon":13.0,"dish":60},
    "eutelsat16":{"name":"Eutelsat 16A 16.0°E","lon":16.0,"dish":80},
    "astra28":{"name":"Astra 28.2°E","lon":28.2,"dish":80},
    "turksat42":{"name":"Türksat 42.0°E","lon":42.0,"dish":80},
    "thor08w":{"name":"Thor 0.8°W","lon":-0.8,"dish":80},
    "eutelsat5w":{"name":"Eutelsat 5 West B 5.0°W","lon":-5.0,"dish":80}
}

TRANSPONDERS = {
    "astra19":[
        {"id":"zdf11347","label":"ZDF Vision / FTA","freq":11347,"pol":"V","sr":22000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["3sat HD","KiKA HD","ZDFinfo HD"],"note":"Ottimo TP di riferimento FTA."},
        {"id":"ard11494","label":"ARD Digital","freq":11494,"pol":"H","sr":22000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["ARD Digital bouquet"],"note":"Secondo TP utile per verifica Astra 19.2E."},
        {"id":"ard10891","label":"ARD Digital","freq":10891,"pol":"H","sr":22000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["ARD Digital bouquet"],"note":"TP basso, utile anche per verificare commutazione banda."}
    ],
    "hotbird13":[
        {"id":"tivusat10992","label":"tivùsat / riferimento ufficiale","freq":10992,"pol":"V","sr":29900,"fec":"auto","system":"DVB-S2","channels":["Servizi tivùsat / Rai secondo lista corrente"],"note":"Frequenza mostrata nelle procedure ufficiali tivùsat."},
        {"id":"tivusat11765","label":"tivùsat / misura segnale","freq":11765,"pol":"V","sr":29900,"fec":"auto","system":"DVB-S2","channels":["Servizi tivùsat secondo lista corrente"],"note":"Usata nelle schermate ufficiali tivùsat per la misura del segnale."},
        {"id":"tivusat11288","label":"tivùsat / Rai","freq":11288,"pol":"V","sr":22000,"fec":"auto","system":"DVB-S2","channels":["Rai 1","Rai 2","Rai 3","Rai 4","Rai Movie","Rai News 24","tivùlink"],"note":"TP mostrato nelle procedure ufficiali tivùsat; composizione soggetta a variazioni."},
        {"id":"fta10719","label":"Hotbird FTA riferimento","freq":10719,"pol":"V","sr":27500,"fec":"auto","system":"DVB-S2","channels":["Canali FTA vari"],"note":"TP alternativo per aggancio Hotbird."}
    ],
    "eutelsat16":[
        {"id":"11283v","label":"A1 / area balcanica","freq":11283,"pol":"V","sr":30000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["FilmBox+ Hits Adria HD","Dizi HD","FightBox HD"],"note":"TP verificato su Eutelsat 16A."}
    ],
    "astra28":[
        {"id":"11023h","label":"BBC / Freesat UK","freq":11023,"pol":"H","sr":23000,"fec":"3/4","system":"DVB-S2 8PSK","channels":["BBC One Scotland HD","BBC One Wales HD","BBC News UK","BBC Alba"],"note":"Beam UK; in Europa continentale può richiedere parabola maggiore."},
        {"id":"11082h","label":"UK Europe beam","freq":11082,"pol":"H","sr":23000,"fec":"2/3","system":"DVB-S2 8PSK","channels":["Now 80's","Now 70's","Rewind TV","Blaze UK"],"note":"Alternativa sul beam europeo."}
    ],
    "turksat42":[
        {"id":"12380v","label":"Türksat West","freq":12380,"pol":"V","sr":27500,"fec":"3/4","system":"DVB-S","channels":["TGRT Haber","Halk TV"],"note":"TP West verificato."}
    ],
    "thor08w":[
        {"id":"11823h","label":"Digi România HD","freq":11823,"pol":"H","sr":30000,"fec":"5/6","system":"DVB-S2 8PSK","channels":["TV 2 Hungary HD","M1 Hungary HD","Digi Sport 1 HD","Digi Sport 2 HD","Pro TV HD","TVR Info","TVR Cultural"],"note":"Ottimo riferimento Digi România."},
        {"id":"11862h","label":"Digi România","freq":11862,"pol":"H","sr":28000,"fec":"7/8","system":"DVB-S","channels":["Bouquet Digi România"],"note":"TP alternativo."},
        {"id":"11900h","label":"Digi România","freq":11900,"pol":"H","sr":28000,"fec":"5/6","system":"DVB-S","channels":["Bouquet Digi România"],"note":"TP alternativo."},
        {"id":"12092h","label":"Digi România","freq":12092,"pol":"H","sr":28000,"fec":"7/8","system":"DVB-S","channels":["Bouquet Digi România"],"note":"TP alternativo."}
    ],
    "eutelsat5w":[
        {"id":"11096v","label":"Fransat","freq":11096,"pol":"V","sr":29950,"fec":"3/4","system":"DVB-S2 8PSK","channels":["TF1 HD","M6 HD","ARTE Français HD","6ter HD","KTO"],"note":"Molti servizi sono criptati Viaccess."}
    ]
}

SYSTEMS={"auto":"Automatico (consigliato)","single":"LNB universale Single","twin":"LNB universale Twin","quad":"LNB universale Quad","octo":"LNB universale Octo","unicable":"SCR / Unicable EN50494","jess":"JESS / dCSS EN50607","quattro":"LNB Quattro + multiswitch","wideband":"LNB Wideband + multiswitch"}
WIDEBAND_LNBS={"generic10410":{"name":"Wideband generico LO 10.41 GHz","lo":10410},"inverto10400":{"name":"Inverto Wideband EU LO 10.40 GHz","lo":10400},"inverto10410":{"name":"Inverto Wideband LO 10.41 GHz","lo":10410},"johansson9720":{"name":"Johansson 9720 Wideband","lo":10410},"triax_twb205":{"name":"TRIAX TWB 205 Wideband","lo":10410},"televes747402":{"name":"Televes 747402 WideBand","lo":10410}}

def look_angles(lat,lon,sat_lon):
    phi=radians(lat); dl=radians(sat_lon-lon); c=cos(phi)*cos(dl); elevation=degrees(atan((c-0.1512)/sqrt(max(1e-12,1-c*c)))); az=degrees(atan2(sin(dl),-sin(phi)*cos(dl))); return round((180+az)%360,1),round(elevation,1),round(degrees(atan2(sin(dl),sin(phi))),1)

def recommend_system(receivers,sat_count):
    if sat_count>2 or receivers>8:return "quattro"
    if receivers<=1 and sat_count==1:return "single"
    if receivers<=2 and sat_count==1:return "twin"
    if receivers<=4 and sat_count==1:return "quad"
    if receivers<=8 and sat_count==1:return "octo"
    return "quattro"

def build_layout(system,receivers,sat_count):
    c=[];w=[]
    if system=="single":c.append(f"{sat_count} × LNB Single");w.append("1 cavo per satellite")
    elif system=="twin":c.append(f"{sat_count} × LNB Twin");w.append("2 uscite indipendenti per LNB")
    elif system=="quad":c.append(f"{sat_count} × LNB Quad");w.append("Fino a 4 linee indipendenti per LNB")
    elif system=="octo":c.append(f"{sat_count} × LNB Octo");w.append("Fino a 8 linee indipendenti per LNB")
    elif system=="quattro":c += [f"{sat_count} × LNB Quattro",f"1 × multiswitch ≥ {sat_count*4} ingressi SAT / {receivers} uscite"];w += [f"{sat_count*4} cavi VL/VH/HL/HH",f"{receivers} linee multiswitch→tuner"]
    elif system=="wideband":c += [f"{sat_count} × LNB Wideband",f"1 × multiswitch Wideband/dCSS ≥ {sat_count*2} ingressi SAT"];w.append(f"{sat_count*2} cavi H+V")
    elif system in ("unicable","jess"):c.append(f"{sat_count} × sorgente compatibile {SYSTEMS[system]}");w.append("Distribuzione su singolo cavo con User Band")
    if sat_count>1 and system in ("single","twin","quad","octo"):c.append("Commutatore DiSEqC");w.append("LNB → DiSEqC → tuner")
    return c,w

def meter_settings(tp,satname,system,diseqc_port=1,wideband_key="generic10410"):
    freq=tp["freq"];pol=tp["pol"];high=freq>=11700;voltage="18 V" if pol=="H" else "13 V";m={"meter":"Amiko X-Finder 3","lnb_type":"Universal (9750/10600)","frequency_mhz":freq,"polarization":pol,"symbol_rate":tp["sr"],"fec":tp["fec"],"dvb":tp["system"],"lnb_voltage":voltage,"tone_22khz":"AUTO (Universal)","lof":"9750 / 10600 MHz","if_mhz":freq-(10600 if high else 9750),"diseqc":"Disable" if diseqc_port==1 else f"DiSEqC 1.0: {diseqc_port}/4","warning":""}
    if system=="wideband":
        wb=WIDEBAND_LNBS.get(wideband_key,WIDEBAND_LNBS["generic10410"]);ifreq=abs(freq-wb["lo"]);ok=950<=ifreq<=2150;m.update({"lnb_type":f"USER → LO {wb['lo']} MHz","tone_22khz":"OFF","lof":f"{wb['lo']} MHz","if_mhz":ifreq,"warning":f"Collega l'uscita {pol} del Wideband. IF {ifreq} MHz: "+("OK per X-Finder 3" if ok else "fuori range 950–2150 MHz")})
    elif system=="unicable":m["lnb_type"]="Unicable"
    elif system=="jess":m["warning"]="X-Finder 3 non mostra JESS come voce separata: verifica firmware/User Band."
    m["steps"]=[f"Satellite: {satname}",f"LNB Type: {m['lnb_type']}",f"TP: {freq} MHz {pol} SR {tp['sr']}",f"LNB Power: {m['lnb_voltage']}",f"22K: {m['tone_22khz']}",f"DiSEqC: {m['diseqc']}","Cerca LOCK e massimizza qualità/MER; controlla BER."]
    return m

@app.route("/")
def index():return render_template("index.html",satellites=SATELLITES,systems=SYSTEMS,wideband_lnbs=WIDEBAND_LNBS,transponders=TRANSPONDERS)

@app.route("/api/geocode",methods=["POST"])
def geocode():
    d=request.get_json(force=True);city=(d.get("city") or "").strip()
    if not city:return jsonify({"error":"Inserisci il nome della città"}),400
    try:
        params=urlencode({"q":city,"format":"jsonv2","limit":5});req=Request("https://nominatim.openstreetmap.org/search?"+params,headers={"User-Agent":"SatelliteInstallerPro/0.5.0"});
        with urlopen(req,timeout=8) as r:data=json.loads(r.read().decode())
        return jsonify({"results":[{"name":x.get("display_name",city),"lat":float(x["lat"]),"lon":float(x["lon"])} for x in data[:5]]})
    except Exception as e:return jsonify({"error":"Ricerca città non disponibile.","detail":str(e)}),502

@app.route("/api/transponders/<sid>")
def transponders(sid):return jsonify({"transponders":TRANSPONDERS.get(sid,[])})

@app.route("/api/calc",methods=["POST"])
def calc():
    d=request.get_json(force=True);lat=float(d["lat"]);lon=float(d["lon"]);ids=[s for s in (d.get("satellites") or ["astra19"]) if s in SATELLITES] or ["astra19"];receivers=max(1,int(d.get("receivers",1)));system=d.get("system","auto");system=recommend_system(receivers,len(ids)) if system=="auto" else system;wb=d.get("wideband_lnb","generic10410");tp_sel=d.get("transponders",{});results=[];dish=0;lons=[]
    for idx,sid in enumerate(ids,1):
        sat=SATELLITES[sid];tps=TRANSPONDERS[sid];tp=next((x for x in tps if x["id"]==tp_sel.get(sid)),tps[0]);az,el,sk=look_angles(lat,lon,sat["lon"]);dish=max(dish,sat["dish"]);lons.append(sat["lon"]);results.append({"id":sid,"satellite":sat["name"],"azimuth":az,"elevation":el,"skew":sk,"transponder":f"{tp['freq']} {tp['pol']} {tp['sr']}","tp_label":tp["label"],"fec":tp["fec"],"dvb_system":tp["system"],"channels":tp["channels"],"tp_note":tp["note"],"meter":meter_settings(tp,sat["name"],system,idx,wb)})
    if len(ids)>1:dish=max(dish+15,80)+(10 if max(lons)-min(lons)>12 else 0)
    c,w=build_layout(system,receivers,len(ids));warnings=[]
    if len(ids)>4:warnings.append("Per più di 4 satelliti valuta multiswitch in cascata o DiSEqC avanzato.")
    if system=="wideband":warnings.append("Wideband: imposta USER con la LO reale del modello e verifica IF 950–2150 MHz.")
    return jsonify({"satellites":results,"dish_min_cm":dish,"system":SYSTEMS[system],"components":c,"wiring":w,"warnings":warnings})

app.run(host="0.0.0.0",port=8099)
