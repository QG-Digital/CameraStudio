# camera ao vivo: simples, bonita e sem inventar moda demais
import base64
import io
import json
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, request
try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None
try:
    from PIL import Image
except ImportError:
    Image = None
try:
    import pyvirtualcam
except ImportError:
    pyvirtualcam = None

try:
    import webview
except ImportError:
    webview = None

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'camera_config.json'
# se der ruim em algum valor, volta pra esse perfil aqui e vida que segue
DEFAULTS = {
    'brightness': 0,
    'contrast': 1.0,
    'saturation': 1.0,
    'exposure': 0.0,
    'mirror': True,
    'auto_mode': False,
    'auto_intensity': 0.0,
    'zoom': 1.0,
    'auto_zoom': False,
    'face_follow': False,
    'face_size': 0.36,
    'face_deadzone': 0.35,
    'face_smoothness': 0.78,
    'virtual_camera': False,
}


def load_config():
    try:
        data = json.loads(CONFIG.read_text(encoding='utf-8'))
    except Exception:
        data = {}
    result = DEFAULTS.copy()
    result.update({k: v for k, v in data.items() if k in DEFAULTS})
    return result


def save_config(data):
    result = DEFAULTS.copy()
    result.update({k: data.get(k, v) for k, v in DEFAULTS.items()})
    CONFIG.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


app = Flask(__name__)
config_lock = threading.RLock()
config = load_config()
virtual_lock = threading.RLock()
virtual_running = False
virtual_frame = None
virtual_thread = None
FACE_CASCADE = None
if cv2 is not None:
    cascade_path = ROOT / 'haarcascade_frontalface_default.xml'
    if cascade_path.exists():
        FACE_CASCADE = cv2.CascadeClassifier(str(cascade_path))


@app.get('/')
def index():
    return HTML


@app.get('/api/config')
def get_config():
    with config_lock:
        return jsonify(config.copy())


@app.post('/api/recording')
def save_recording():
    data = request.get_data(cache=False)
    if not data:
        return jsonify({'ok': False, 'msg': 'Gravação vazia.'}), 400
    downloads = Path.home() / 'Downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    filename = 'camera_studio_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.webm'
    target = downloads / filename
    target.write_bytes(data)
    return jsonify({'ok': True, 'filename': filename, 'path': str(target), 'bytes': len(data)})

@app.post('/api/virtual/start')
def start_virtual():
    global virtual_running, virtual_thread
    if pyvirtualcam is None or Image is None:
        return jsonify({'ok': False, 'msg': 'Instale pyvirtualcam e Pillow para usar a câmera virtual.'}), 400
    with virtual_lock:
        if virtual_running:
            return jsonify({'ok': True, 'msg': 'Câmera virtual já está ativa.'})
        virtual_running = True
    virtual_thread = threading.Thread(target=virtual_loop, daemon=True)
    virtual_thread.start()
    return jsonify({'ok': True, 'msg': 'Câmera virtual ativa para o OBS.'})

@app.post('/api/virtual/stop')
def stop_virtual():
    global virtual_running, virtual_frame
    with virtual_lock:
        virtual_running = False
        virtual_frame = None
    return jsonify({'ok': True, 'msg': 'Câmera virtual desativada.'})

@app.post('/api/virtual/frame')
def virtual_frame_api():
    global virtual_frame
    raw = request.get_json(silent=True) or {}
    encoded = str(raw.get('data', ''))
    if not encoded:
        return jsonify({'ok': False}), 400
    try:
        payload = encoded.split(',', 1)[-1]
        image = Image.open(io.BytesIO(base64.b64decode(payload))).convert('RGB')
        with virtual_lock:
            if virtual_running:
                virtual_frame = image.copy()
        return jsonify({'ok': True})
    except Exception as exc:
        return jsonify({'ok': False, 'msg': str(exc)}), 400

# o OBS gosta de frame chegando certinho. se atrasar, ele fica emburrado.
def virtual_loop():
    global virtual_running, virtual_frame
    cam = None
    try:
        cam = pyvirtualcam.Camera(width=640, height=360, fps=20, backend='obs')
        while True:
            with virtual_lock:
                active = virtual_running
                image = None if virtual_frame is None else virtual_frame.copy()
            if not active:
                break
            if image is not None:
                frame = image.resize((640, 360))
                cam.send(__import__('numpy').array(frame))
            cam.sleep_until_next_frame()
    except Exception as exc:
        print('[PYTHON] Câmera virtual:', exc, flush=True)
    finally:
        if cam is not None:
            try:
                cam.close()
            except Exception:
                pass
        with virtual_lock:
            virtual_running = False
            virtual_frame = None

# aqui o Python olha só um quadradinho pequeno. nada de carregar o mundo nas costas.
@app.post('/api/face')
def detect_face():
    if cv2 is None or np is None or FACE_CASCADE is None:
        return jsonify({'ok': False, 'faces': [], 'msg': 'Detector facial Python indisponível.'}), 503
    payload = request.get_data(cache=False)
    if not payload:
        return jsonify({'ok': False, 'faces': []}), 400
    try:
        image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            return jsonify({'ok': False, 'faces': []}), 400
        faces = FACE_CASCADE.detectMultiScale(image, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        return jsonify({'ok': True, 'faces': [{'x': int(x), 'y': int(y), 'width': int(w), 'height': int(h), 'frame_width': int(image.shape[1]), 'frame_height': int(image.shape[0])} for x, y, w, h in faces]})
    except Exception as exc:
        return jsonify({'ok': False, 'faces': [], 'msg': str(exc)}), 400

@app.post('/api/config')
def update_config():
    global config
    data = request.get_json(silent=True) or {}
    with config_lock:
        config.update({k: v for k, v in data.items() if k in DEFAULTS})
        config = save_config(config)
        return jsonify(config.copy())


# daqui pra baixo é a parte bonitinha: navegador fazendo o trabalho leve em tempo real.
HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Camera Studio — Ao vivo</title>
<style>
:root{--green:#087f5b;--green2:#0ca678;--ink:#17332b;--muted:#71827d;--line:#dfe9e4;--soft:#f4faf7;--white:#fff;--red:#c2414d}
*{box-sizing:border-box}body{margin:0;background:#f7faf9;color:var(--ink);font:14px Segoe UI,Arial,sans-serif}body.camera-only{background:#000;overflow:hidden}body.camera-only header,body.camera-only .intro,body.camera-only aside{display:none}body.camera-only main.wrap{max-width:none;width:100vw;height:100vh;margin:0;padding:0}body.camera-only .layout{display:block;width:100vw;height:100vh}body.camera-only .layout section.card{width:100vw;height:100vh;padding:0;border:0;border-radius:0;box-shadow:none;background:#000}body.camera-only .preview{width:100vw;height:100vh;min-height:0;border-radius:0}body.camera-only .preview video{object-fit:cover}body.camera-only .preview .live-label{display:none}#exitFillCamera{display:none;position:fixed;right:18px;top:18px;z-index:20;border:1px solid #ffffff66;border-radius:9px;padding:10px 14px;background:#10251dcc;color:#fff;font-weight:700;cursor:pointer;backdrop-filter:blur(5px)}body.camera-only #exitFillCamera{display:block}
header{height:72px;background:#fff;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 30px}.brand{display:flex;align-items:center;gap:12px}.mark{width:38px;height:38px;border-radius:12px;background:linear-gradient(145deg,var(--green2),var(--green));color:#fff;display:grid;place-items:center;font-weight:900;font-size:17px}.brand h1{margin:0;font-size:18px}.brand span{display:block;color:var(--muted);font-size:11px;margin-top:2px}.status{border-radius:20px;padding:8px 13px;background:#f0fbf5;border:1px solid #bde5d2;color:var(--green);font-weight:700}
.wrap{max-width:1250px;margin:auto;padding:24px 30px}.intro{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:18px}.intro h2{margin:0;font-size:24px}.intro p{margin:5px 0;color:var(--muted)}.actions{display:flex;gap:8px}.btn{border:0;border-radius:9px;padding:10px 14px;background:var(--green);color:#fff;font-weight:700;cursor:pointer;transition:background .2s,transform .2s}.btn:hover{transform:translateY(-1px)}.btn.gray{background:#c7cfcc;color:#52615b}.btn.auto{background:#356bb3}.btn.auto.on{background:#8b63d2}.card{background:#fff;border:1px solid var(--line);border-radius:15px;box-shadow:0 6px 20px #153d2b0b;padding:18px}.layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:18px}.preview{position:relative;background:#101a16;border-radius:12px;min-height:520px;display:grid;place-items:center;overflow:hidden}.preview video{width:100%;height:100%;object-fit:contain;display:none;background:#101a16}.live-label{position:static;display:inline-block;margin-bottom:8px}.preview.fill-camera video{object-fit:cover}.preview.fill-camera .live-label{display:none}.empty{color:#b8c9c1;text-align:center;padding:30px}.live-label{z-index:2;background:#10251dcc;border:1px solid #4a7863;color:#d8f3e5;border-radius:7px;padding:6px 9px;font-size:11px;font-weight:800}.card h3{margin:0 0 16px;font-size:15px}.control{display:grid;grid-template-columns:1fr 62px;gap:8px;align-items:center;margin:16px 0}.control label{font-weight:650}.control input[type=range]{grid-column:1;width:100%;accent-color:var(--green);transition:filter .25s}.control output{grid-column:2;grid-row:1/3;text-align:right;color:var(--green);font-weight:800}.hint{background:var(--soft);border:1px solid #d7eee2;border-radius:10px;padding:12px;color:var(--green);font-size:12px;line-height:1.45;margin-top:18px}.auto-box{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px;border:1px solid #d9d0f3;background:#faf8ff;border-radius:10px;margin-bottom:12px}.auto-intensity{margin:10px 0 18px;padding:10px 12px;border:1px solid #e7e1f7;border-radius:10px;background:#fcfbff}.auto-intensity input[type=range]{accent-color:#7657c7}.auto-box strong{display:block}.zoom-auto-box{margin-top:12px}.auto-box small{display:block;color:var(--muted);margin-top:3px}.toggle{width:45px;height:25px;border-radius:20px;border:0;background:#bfc8c4;position:relative;cursor:pointer;transition:.25s}.toggle:after{content:"";position:absolute;width:19px;height:19px;left:3px;top:3px;border-radius:50%;background:#fff;transition:.25s}.toggle.on{background:#7657c7}.toggle.on:after{left:23px}@media(max-width:900px){.layout{grid-template-columns:1fr}.intro{display:block}.actions{margin-top:14px}.preview{min-height:400px}}@media(max-width:560px){.wrap{padding:18px 14px}.preview{min-height:280px}.control{margin:13px 0}}
</style>
</head>
<body>
<header><div class="brand"><div class="mark">C</div><div><h1>Camera Studio</h1><span>Imagem ao vivo, simples e estável</span></div></div><div id="status" class="status">Câmera desligada</div></header>
<main class="wrap"><div class="intro"><div><h2>Minha câmera ao vivo</h2><p>Sem pós-processamento pesado: apenas ajustes leves e instantâneos.</p></div><div class="actions"><button id="start" class="btn" onclick="startCamera()">Ligar câmera</button><button id="stop" class="btn gray" onclick="stopCamera()">Parar</button><button id="record" class="btn gray" onclick="toggleRecording()">Gravar câmera</button><button id="fillCamera" class="btn gray" onclick="toggleFillCamera()" aria-pressed="false">Preencher câmera</button><button id="virtual" class="btn gray" onclick="toggleVirtual()">Câmera virtual OBS</button></div></div>
<button id="exitFillCamera" onclick="toggleFillCamera()" aria-label="Voltar ao modo normal">Voltar ao modo normal</button><div class="layout"><section class="card"><div class="live-label">CÂMERA AO VIVO</div><div class="preview"><video id="video" autoplay muted playsinline></video><div id="empty" class="empty">Clique em “Ligar câmera” para começar.</div><canvas id="recordCanvas" width=1280 height=720 style="display:none"></canvas></div></section>
<aside class="card"><h3>Ajustes leves</h3><div class="auto-box"><div><strong>Modo automático</strong><small id="autoText">Desligado — ajuste manual</small></div><button id="autoToggle" class="toggle" aria-label="Modo automático" onclick="toggleAuto()"></button></div><div class="auto-intensity"><div class="control" style="margin:0"><label for="auto_intensity">Intensidade do Auto</label><output id="auto_intensityOut">0.00</output><input id="auto_intensity" type="range" min="-1" max="1" step="0.01" data-key="auto_intensity"></div><small style="color:var(--muted)">− discreto&nbsp;&nbsp;|&nbsp;&nbsp;0 normal&nbsp;&nbsp;|&nbsp;&nbsp;+ exagerado</small></div>
<div class="control"><label for="brightness">Brilho</label><output id="brightnessOut">0</output><input id="brightness" type="range" min="-100" max="100" step="1" data-key="brightness"></div>
<div class="control"><label for="contrast">Contraste</label><output id="contrastOut">1.00</output><input id="contrast" type="range" min="0.5" max="1.8" step="0.01" data-key="contrast"></div>
<div class="control"><label for="saturation">Saturação</label><output id="saturationOut">1.00</output><input id="saturation" type="range" min="0" max="2" step="0.01" data-key="saturation"></div>
<div class="control"><label for="exposure">Exposição</label><output id="exposureOut">0.00</output><input id="exposure" type="range" min="-2" max="2" step="0.01" data-key="exposure"></div>
<div class="control"><label for="zoom">Zoom</label><output id="zoomOut">1.00x</output><input id="zoom" type="range" min="1" max="2.5" step="0.01" data-key="zoom"></div><div class="auto-box zoom-auto-box"><div><strong>Zoom automático</strong><small id="zoomAutoText">Desligado — enquadramento manual</small></div><button id="zoomAutoToggle" class="toggle" aria-label="Zoom automático" onclick="toggleZoomAuto()"></button></div><div class="auto-box zoom-auto-box"><div><strong>Seguir meu rosto</strong><small id="faceFollowText">Desligado — câmera parada</small></div><button id="faceFollowToggle" class="toggle" aria-label="Seguir meu rosto" onclick="toggleFaceFollow()"></button></div><div class="control"><label for="face_size">Tamanho no quadro</label><output id="face_sizeOut">0.36</output><input id="face_size" type="range" min="0.22" max="0.55" step="0.01" data-key="face_size"></div><div class="control"><label for="face_deadzone">Distância para seguir</label><output id="face_deadzoneOut">0.35</output><input id="face_deadzone" type="range" min="0" max="1" step="0.01" data-key="face_deadzone"></div><div class="control"><label for="face_smoothness">Suavidade do movimento</label><output id="face_smoothnessOut">0.78</output><input id="face_smoothness" type="range" min="0.25" max="0.95" step="0.01" data-key="face_smoothness"></div><div class="control"><label for="mirror">Espelhar câmera</label><output></output><input id="mirror" type="checkbox" data-key="mirror" style="width:20px;height:20px;accent-color:var(--green)"></div>
<div class="hint">O botão <strong>Gravar câmera</strong> salva somente a câmera em Downloads. O botão <strong>Câmera virtual OBS</strong> cria uma fonte virtual quando o OBS Virtual Camera estiver instalado. O modo automático usa uma leitura leve da luminosidade do próprio vídeo. Ele parte da configuração atual e movimenta os controles suavemente, sem enviar frames para o Python e sem bloquear a câmera.</div></aside></div></main>
<script>
// buga-buga central: se o vídeo está vivo, já temos meio caminho andado.
const $=id=>document.getElementById(id);let cfg={},stream=null,autoTimer=null,autoBase=null,animating=false,mediaRecorder=null,recordChunks=[],recordCanvas=null,recordCtx=null,recordLoop=null,virtualOn=false,virtualTimer=null,faceDetector=null,zoomTimer=null,zoomBase=1,panX=0,panY=0,followAnimation=null,lastCandidateZoom=1,candidateZoomCount=0,fillCameraOn=false;
function output(key,v){const o=$(key+'Out');if(o)o.textContent=key==='brightness'?Math.round(v):key==='zoom'?Number(v).toFixed(2)+'x':Number(v).toFixed(2)}
function setControl(k,v){const e=$(k);if(!e)return;if(e.type==='checkbox')e.checked=!!v;else e.value=v;output(k,v)}
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});return await r.json()}
function visualFilter(){const b=Number(cfg.brightness||0);const c=Number(cfg.contrast||1);const s=Number(cfg.saturation||1);const e=Math.pow(2,Number(cfg.exposure||0));return `brightness(${Math.max(.05,(1+b/100)*e).toFixed(3)}) contrast(${c.toFixed(3)}) saturate(${s.toFixed(3)})`}
function apply(){const v=$('video');const zoom=Math.max(1,Math.min(2.5,Number(cfg.zoom||1)));v.style.filter=visualFilter();v.style.transform=`translate(${Math.max(-18,Math.min(18,panX)).toFixed(2)}%,${Math.max(-18,Math.min(18,panY)).toFixed(2)}%) ${cfg.mirror?'scaleX(-1) ':''}scale(${zoom.toFixed(3)})`}
function toggleFillCamera(){fillCameraOn=!fillCameraOn;document.body.classList.toggle('camera-only',fillCameraOn);const preview=document.querySelector('.preview');preview.classList.toggle('fill-camera',fillCameraOn);const button=$('fillCamera');button.textContent=fillCameraOn?'Voltar ao enquadramento':'Preencher câmera';button.classList.toggle('auto',fillCameraOn);button.classList.toggle('on',fillCameraOn);button.classList.toggle('gray',!fillCameraOn);button.setAttribute('aria-pressed',String(fillCameraOn))}
function updateAutoUi(){const on=!!cfg.auto_mode;const intensity=Number(cfg.auto_intensity||0);$('autoToggle').classList.toggle('on',on);$('autoText').textContent=on?'Ligado — intensidade '+(intensity>0?'exagerada':intensity<0?'discreta':'normal'):'Desligado — ajuste manual'}
function updateZoomUi(){const on=!!cfg.auto_zoom;$('zoomAutoToggle').classList.toggle('on',on);$('zoomAutoText').textContent=on?'Ligado — enquadramento automático':'Desligado — enquadramento manual'}
function updateFaceFollowUi(){const on=!!cfg.face_follow;$('faceFollowToggle').classList.toggle('on',on);$('faceFollowText').textContent=on?'Ligado — acompanhando seu rosto':'Desligado — câmera parada'}
async function saveOne(k,v){cfg[k]=v;output(k,v);apply();await api('/api/config',{method:'POST',body:JSON.stringify({[k]:v})})}
function animateTo(target,duration=420){const from={brightness:Number(cfg.brightness||0),contrast:Number(cfg.contrast||1),saturation:Number(cfg.saturation||1),exposure:Number(cfg.exposure||0)};const start=performance.now();function step(now){const p=Math.min(1,(now-start)/duration),q=p*p*(3-2*p);for(const k of Object.keys(target)){const v=from[k]+(target[k]-from[k])*q;cfg[k]=v;setControl(k,v)}apply();if(p<1)requestAnimationFrame(step);else{for(const k of Object.keys(target))cfg[k]=target[k];saveAuto(target)}}requestAnimationFrame(step)}
async function saveAuto(target){await api('/api/config',{method:'POST',body:JSON.stringify(target)})}
async function saveZoom(v){cfg.zoom=v;output('zoom',v);apply();await api('/api/config',{method:'POST',body:JSON.stringify({zoom:v})})}
function animateZoom(target,duration=500){const from=Number(cfg.zoom||1),start=performance.now();function step(now){const p=Math.min(1,(now-start)/duration),q=p*p*(3-2*p);cfg.zoom=from+(target-from)*q;setControl('zoom',cfg.zoom);apply();if(p<1)requestAnimationFrame(step);else saveZoom(target)}requestAnimationFrame(step)}
// manda um mini quadro pro Python, porque a gente não precisa acordar o dragão inteiro.
let faceBusy=false;async function detectFacePython(){
if(faceBusy||!stream)return[];faceBusy=true;try{const c=document.createElement('canvas');c.width=320;c.height=180;c.getContext('2d').drawImage($('video'),0,0,c.width,c.height);const blob=await new Promise(res=>c.toBlob(res,'image/jpeg',.58));const r=await fetch('/api/face',{method:'POST',headers:{'Content-Type':'image/jpeg'},body:blob});const data=await r.json();return data.ok?data.faces:[]}catch(e){return[]}finally{faceBusy=false}}
function animateFollow(target,duration){cancelAnimationFrame(followAnimation);const from={x:panX,y:panY,z:Number(cfg.zoom||1)};const start=performance.now();const smooth=Number(cfg.face_smoothness||.78);const actualDuration=Math.max(650,duration+(1-smooth)*1400);function step(now){const p=Math.min(1,(now-start)/actualDuration),q=p*p*(3-2*p);panX=from.x+(target.x-from.x)*q;panY=from.y+(target.y-from.y)*q;cfg.zoom=from.z+(target.z-from.z)*q;setControl('zoom',cfg.zoom);apply();if(p<1)followAnimation=requestAnimationFrame(step);else{cfg.zoom=target.z;saveZoom(target.z)}}followAnimation=requestAnimationFrame(step)}
// se o detector inventar um zoom absurdo, aqui ele toma um chega-pra-lá educado.
async function trackFaceStep(){
if((!cfg.auto_zoom&&!cfg.face_follow)||!stream)return;try{const faces=await detectFacePython();if(!faces.length)return;const box=faces[0],fw=Math.max(1,box.frame_width),fh=Math.max(1,box.frame_height);const cx=(box.x+box.width/2)/fw,cy=(box.y+box.height/2)/fh,ratio=box.width/fw;const deadzone=.02+.20*Number(cfg.face_deadzone||0);const desiredX=Math.abs(cx-.5)>deadzone?((cfg.mirror?(cx-.5):(.5-cx))*34):0;const desiredY=Math.abs(cy-.5)>deadzone?((.5-cy)*24):0;const targetSize=Math.max(.22,Math.min(.55,Number(cfg.face_size||.36)));const rawZoom=Math.max(1,Math.min(2.5,targetSize/Math.max(.12,ratio)));const currentZoom=Number(cfg.zoom||1);const rawDelta=rawZoom-currentZoom;if(Math.abs(rawDelta)>.28){if(Math.abs(rawZoom-lastCandidateZoom)<.12)candidateZoomCount++;else{lastCandidateZoom=rawZoom;candidateZoomCount=1}if(candidateZoomCount<3)return}else{candidateZoomCount=0;lastCandidateZoom=rawZoom}const maxStep=.08+.08*(1-Number(cfg.face_smoothness||.78));const safeZoom=currentZoom+Math.max(-maxStep,Math.min(maxStep,rawDelta));animateFollow({x:cfg.face_follow?desiredX:panX,y:cfg.face_follow?desiredY:panY,z:cfg.auto_zoom?safeZoom:currentZoom},850)}catch(e){}}
function restartFaceLoop(){clearInterval(zoomTimer);if((cfg.auto_zoom||cfg.face_follow)&&stream){zoomTimer=setInterval(trackFaceStep,850);trackFaceStep()}}
async function toggleZoomAuto(){cfg.auto_zoom=!cfg.auto_zoom;updateZoomUi();await api('/api/config',{method:'POST',body:JSON.stringify({auto_zoom:cfg.auto_zoom})});restartFaceLoop()}
function toggleFaceFollow(){cfg.face_follow=!cfg.face_follow;updateFaceFollowUi();if(!cfg.face_follow){animateFollow({x:0,y:0,z:Number(cfg.zoom||1)},750)}api('/api/config',{method:'POST',body:JSON.stringify({face_follow:cfg.face_follow})});restartFaceLoop()}
function readLight(){if(!stream||$('video').readyState<2||!$('video').videoWidth)return null;const v=$('video');const c=document.createElement('canvas');c.width=64;c.height=36;const x=c.getContext('2d',{willReadFrequently:true});x.drawImage(v,0,0,c.width,c.height);const d=x.getImageData(0,0,c.width,c.height).data;let sum=0,shadow=0,highlight=0;for(let i=0;i<d.length;i+=4){const y=(.2126*d[i]+.7152*d[i+1]+.0722*d[i+2])/255;sum+=y;if(y<.18)shadow++;if(y>.88)highlight++}return {mean:sum/(d.length/4),shadow:shadow/(d.length/4),highlight:highlight/(d.length/4)}}
// a luz deu uma variada? calma, Auto. mexe devagar que ninguém tá com pressa.
function autoStep(){const l=readLight();
if(!l||!autoBase)return;const intensity=Number(cfg.auto_intensity||0);const strength=Math.max(0,1+intensity);const delta=Math.max(-.75,Math.min(.75,(.48-l.mean)*1.7));const target={brightness:Math.max(-100,Math.min(100,autoBase.brightness+delta*28*strength)),exposure:Math.max(-2,Math.min(2,autoBase.exposure+delta*.72*strength)),contrast:Math.max(.5,Math.min(1.8,autoBase.contrast+(l.highlight-l.shadow)*.16*strength)),saturation:autoBase.saturation};animateTo(target,600)}
function startAutoLoop(){clearInterval(autoTimer);autoTimer=setInterval(autoStep,1100);autoStep()}
function toggleAuto(){if(cfg.auto_mode){cfg.auto_mode=false;updateAutoUi();clearInterval(autoTimer);api('/api/config',{method:'POST',body:JSON.stringify({auto_mode:false})});return}autoBase={brightness:Number(cfg.brightness||0),contrast:Number(cfg.contrast||1),saturation:Number(cfg.saturation||1),exposure:Number(cfg.exposure||0)};cfg.auto_mode=true;updateAutoUi();api('/api/config',{method:'POST',body:JSON.stringify({auto_mode:true})});startAutoLoop()}
async function startCamera(){try{if(!navigator.mediaDevices?.getUserMedia)throw new Error('Este ambiente não liberou acesso à câmera');stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720}},audio:false});$('video').srcObject=stream;await $('video').play();$('video').style.display='block';$('empty').style.display='none';$('status').textContent='Câmera ao vivo';$('status').style.color='var(--green)';$('start').disabled=true;apply()}catch(e){$('status').textContent='Erro na câmera';$('status').style.color='var(--red)';alert(e.message||'Não foi possível abrir a câmera')}}
function stopCamera(){stopRecording();if(cfg.auto_zoom){cfg.auto_zoom=false;clearInterval(zoomTimer);updateZoomUi()}if(cfg.face_follow){cfg.face_follow=false;clearInterval(zoomTimer);updateFaceFollowUi();panX=0;panY=0}if(virtualOn)toggleVirtual();if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}$('video').srcObject=null;$('video').style.display='none';$('empty').style.display='block';$('status').textContent='Câmera desligada';$('start').disabled=false;clearInterval(autoTimer)}
function recordingCanvas(){if(!recordCanvas){recordCanvas=$('recordCanvas');recordCtx=recordCanvas.getContext('2d')}recordCanvas.width=$('video').videoWidth||1280;recordCanvas.height=$('video').videoHeight||720;recordCtx.save();recordCtx.clearRect(0,0,recordCanvas.width,recordCanvas.height);recordCtx.filter=visualFilter();if(cfg.mirror){recordCtx.translate(recordCanvas.width,0);recordCtx.scale(-1,1)}const z=Math.max(1,Math.min(2.5,Number(cfg.zoom||1)));const sw=recordCanvas.width/z,sh=recordCanvas.height/z;const sx=Math.max(0,Math.min(recordCanvas.width-sw,(recordCanvas.width-sw)/2-(panX/100)*recordCanvas.width));const sy=Math.max(0,Math.min(recordCanvas.height-sh,(recordCanvas.height-sh)/2-(panY/100)*recordCanvas.height));recordCtx.drawImage($('video'),sx,sy,sw,sh,0,0,recordCanvas.width,recordCanvas.height);recordCtx.restore()}
function recordingTick(){if(mediaRecorder&&mediaRecorder.state==='recording'){recordingCanvas();recordLoop=requestAnimationFrame(recordingTick)}}
async function toggleRecording(){if(!stream){alert('Ligue a câmera antes de gravar.');return}if(mediaRecorder&&mediaRecorder.state==='recording'){mediaRecorder.stop();return}recordChunks=[];recordingCanvas();const source=recordCanvas.captureStream(30);const preferred='video/webm;codecs=vp8';const recorderOptions=MediaRecorder.isTypeSupported(preferred)?{mimeType:preferred,videoBitsPerSecond:6000000}:{videoBitsPerSecond:6000000};mediaRecorder=new MediaRecorder(source,recorderOptions);mediaRecorder.ondataavailable=e=>{if(e.data.size)recordChunks.push(e.data)};mediaRecorder.onstop=async()=>{cancelAnimationFrame(recordLoop);const blob=new Blob(recordChunks,{type:'video/webm'});const r=await fetch('/api/recording',{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:blob});const x=await r.json();$('record').textContent='Gravar câmera';$('record').className='btn gray';alert(x.ok?'Gravação salva em Downloads: '+x.filename:'Falha ao salvar: '+x.msg)};mediaRecorder.start(250);$('record').textContent='Parar gravação';$('record').className='btn auto on';recordingTick()}
function stopRecording(){if(mediaRecorder&&mediaRecorder.state==='recording')mediaRecorder.stop()}
async function toggleVirtual(){if(!stream){alert('Ligue a câmera antes de ativar a câmera virtual.');return}if(virtualOn){await api('/api/virtual/stop',{method:'POST'});virtualOn=false;clearInterval(virtualTimer);$('virtual').textContent='Câmera virtual OBS';$('virtual').className='btn gray';return}const r=await api('/api/virtual/start',{method:'POST'});if(!r.ok){alert(r.msg);return}virtualOn=true;$('virtual').textContent='Parar câmera virtual';$('virtual').className='btn auto on';clearInterval(virtualTimer);virtualTimer=setInterval(async()=>{if(!virtualOn||!stream)return;recordingCanvas();const blob=await new Promise(res=>recordCanvas.toBlob(res,'image/jpeg',.72));const reader=new FileReader();reader.onload=()=>fetch('/api/virtual/frame',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({data:reader.result})});reader.readAsDataURL(blob)},70)}
async function load(){cfg=await api('/api/config');for(const k of Object.keys(cfg))setControl(k,cfg[k]);updateAutoUi();updateZoomUi();updateFaceFollowUi();apply()}
document.querySelectorAll('[data-key]').forEach(e=>{e.addEventListener('input',async ev=>{const k=ev.target.dataset.key;if(k==='auto_mode')return;if(cfg.auto_mode&&k!=='mirror'&&k!=='auto_intensity'&&k!=='zoom'){cfg.auto_mode=false;clearInterval(autoTimer);updateAutoUi();await api('/api/config',{method:'POST',body:JSON.stringify({auto_mode:false})})}if(k==='zoom'&&cfg.auto_zoom){cfg.auto_zoom=false;clearInterval(zoomTimer);updateZoomUi();await api('/api/config',{method:'POST',body:JSON.stringify({auto_zoom:false})})}await saveOne(k,ev.target.type==='checkbox'?ev.target.checked:Number(ev.target.value))});e.addEventListener('change',()=>{if(e.type==='checkbox')saveOne(e.dataset.key,e.checked)})});load();
</script></body></html>'''


def run():
    from werkzeug.serving import make_server
    server = make_server('127.0.0.1', 8899, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print('[PYTHON] Camera Studio simples iniciado.', flush=True)
    if webview:
        webview.create_window('Camera Studio — Ao vivo', 'http://127.0.0.1:8899', width=1200, height=820, min_size=(900, 600))
        webview.start()
    else:
        webbrowser.open('http://127.0.0.1:8899')
        print('[PYTHON] Instale pywebview para usar a janela desktop.', flush=True)


if __name__ == '__main__':
    run()
