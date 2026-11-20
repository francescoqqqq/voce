#@title ▶ Avvia il motore (la prima volta 15-20 minuti, poi 3-4)
#@markdown Premi ▶ e aspetta. Alla fine compare un link: aprilo e la pagina Voce si collega da sola.
#@markdown Tieni aperta questa scheda di Colab finché usi la pagina.
import os, re, json, time, secrets, pathlib, subprocess, urllib.request
from IPython.display import display, HTML

PORTA = 7860
PAGINA = 'https://francescoqqqq.github.io/voce/'
def passo(t): print(f'• {t}', flush=True)
def sh(cmd): subprocess.run(cmd, shell=True, check=True)

# 0) GPU
gpu = subprocess.run('nvidia-smi --query-gpu=name --format=csv,noheader', shell=True, capture_output=True, text=True).stdout.strip()
if not gpu:
    raise SystemExit('Nessuna GPU: Runtime → Cambia tipo di runtime → T4 GPU, poi rilancia.')
passo(f'GPU: {gpu}')

# 1) installazione (solo se manca)
os.chdir('/content')
if not os.path.exists('/content/fish-speech/.venv/bin/python'):
    passo('Installo fish-speech (5-8 minuti)...')
    sh('apt-get -qq install -y portaudio19-dev libsox-dev ffmpeg > /dev/null')
    if not os.path.exists('fish-speech'):
        sh('git clone -q --depth 1 https://github.com/fishaudio/fish-speech.git')
    os.chdir('/content/fish-speech')
    sh('pip -q install uv')
    sh('uv sync -q --python 3.12 --extra cu126')
os.chdir('/content/fish-speech')

# 2) modello (solo se manca, ~10 GB)
if not os.path.exists('checkpoints/s2-pro/model-00002-of-00002.safetensors'):
    passo('Scarico il modello S2 Pro (circa 10 GB)...')
    sh('.venv/bin/hf download fishaudio/s2-pro --local-dir checkpoints/s2-pro > /dev/null 2>&1')

# 3) correzioni per la T4 (16 GB di GPU, ~13 GB di RAM)
passo('Adatto il modello alla T4...')
cfg = pathlib.Path('checkpoints/s2-pro/config.json')
d = json.loads(cfg.read_text()); d['text_config']['max_seq_len'] = 8192
cfg.write_text(json.dumps(d, indent=2))

p = pathlib.Path('fish_speech/models/text2semantic/llama.py'); s = p.read_text()
if '_lowram' not in s:
    a = "        model = model_cls(config)\n"
    b = '''        import os as _os
        _lowram = _os.environ.get("FISH_LOW_RAM") == "1"
        if _lowram:
            with torch.device("meta"):
                model = model_cls(config)
            model = model.to(dtype=torch.float16).to_empty(device="cuda")
            model.freqs_cis = precompute_freqs_cis(config.max_seq_len, config.head_dim, config.rope_base).to("cuda")
            model.causal_mask = torch.tril(torch.ones(config.max_seq_len, config.max_seq_len, dtype=torch.bool, device="cuda"))
            if hasattr(model, "fast_freqs_cis"):
                model.fast_freqs_cis = precompute_freqs_cis(config.num_codebooks, config.fast_head_dim, config.rope_base).to("cuda")
        else:
            model = model_cls(config)
'''
    c = '''                for shard in shard_files:
                    weights.update(st_load_file(str(path_obj / shard), device="cpu"))
                weights = _remap_fish_qwen3_omni_keys(weights)
'''
    e = '''                if _lowram:
                    _missing = set(model.state_dict().keys())
                    for shard in shard_files:
                        _w = _remap_fish_qwen3_omni_keys(OrderedDict(st_load_file(str(path_obj / shard), device="cpu")))
                        model.load_state_dict(_w, strict=False)
                        _missing -= set(_w.keys())
                        del _w
                    logger.info(f"Low-RAM load, chiavi mancanti: {sorted(_missing)}")
                else:
                    for shard in shard_files:
                        weights.update(st_load_file(str(path_obj / shard), device="cpu"))
                    weights = _remap_fish_qwen3_omni_keys(weights)
'''
    assert s.count(a) == 1 and s.count(c) == 1, 'Il codice di fish-speech è cambiato: avvisa Claude'
    p.write_text(s.replace(a, b).replace(c, e))

q = pathlib.Path('fish_speech/models/dac/modded_dac.py')
q.write_text(q.read_text().replace('torch.ones(32768, 32768, dtype=torch.bool)', 'torch.ones(8192, 8192, dtype=torch.bool)'))

# la pagina Voce sta su un altro indirizzo e manda la chiave: il server deve accettarla
srv = pathlib.Path('tools/api_server.py'); t = srv.read_text()
if 'cors_config=CORSConfig(),' in t:
    srv.write_text(t.replace('cors_config=CORSConfig(),', 'cors_config=CORSConfig(allow_headers=["Authorization"]),'))

# 4) avvio server con chiave
subprocess.run(['pkill', '-f', 'tools/api_server.py']); subprocess.run(['pkill', '-f', 'cloudflared']); time.sleep(3)
CHIAVE = secrets.token_urlsafe(18)
env = dict(os.environ, FISH_LOW_RAM='1', PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
passo('Carico il modello sulla GPU (2-3 minuti)...')
server = subprocess.Popen(
    ['.venv/bin/python', 'tools/api_server.py', '--listen', f'0.0.0.0:{PORTA}',
     '--llama-checkpoint-path', 'checkpoints/s2-pro',
     '--decoder-checkpoint-path', 'checkpoints/s2-pro/codec.pth',
     '--decoder-config-name', 'modded_dac_vq', '--half', '--api-key', CHIAVE],
    stdout=open('/content/server.log', 'w'), stderr=subprocess.STDOUT, env=env)
pronto = False
for i in range(150):
    time.sleep(4)
    try:
        r = urllib.request.Request(f'http://127.0.0.1:{PORTA}/v1/health', headers={'Authorization': f'Bearer {CHIAVE}'})
        if b'ok' in urllib.request.urlopen(r, timeout=3).read():
            pronto = True; break
    except Exception:
        pass
    if server.poll() is not None:
        break
if not pronto:
    print('❌ Il server non è partito. Ultime righe del log (copiale a Claude):')
    print(open('/content/server.log').read()[-2500:])
    raise SystemExit()
passo('Modello pronto ✅')

# 5) tunnel pubblico (Cloudflare, gratuito, indirizzo nuovo a ogni avvio)
if not os.path.exists('/content/cloudflared'):
    sh('wget -q -O /content/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x /content/cloudflared')
tlog = open('/content/tunnel.log', 'w')
tunnel = subprocess.Popen(['/content/cloudflared', 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{PORTA}'],
                          stdout=tlog, stderr=subprocess.STDOUT)
URL = None
for i in range(60):
    time.sleep(1)
    m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', open('/content/tunnel.log').read())
    if m: URL = m.group(0); break
if not URL:
    print('❌ Tunnel non partito:'); print(open('/content/tunnel.log').read()[-1500:]); raise SystemExit()

link = f'{PAGINA}#motore={URL}&chiave={CHIAVE}'
passo('Tutto pronto ✅')
display(HTML(f'<p style="font-size:18px">👉 <a href="{link}" target="_blank"><b>Apri Voce collegata a questo motore</b></a></p>'
             f'<p style="color:gray">Oppure nella pagina incolla a mano:<br>motore: <code>{URL}</code><br>chiave: <code>{CHIAVE}</code></p>'))
