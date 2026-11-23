"""Load the model at increasing num_ctx and record VRAM / GPU-CPU split and speed."""
import json, os, re, subprocess, sys, time, urllib.request

DEFAULT_MODEL = "gemma4:e4b-it-q4_K_M"


def _pop_opt(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        v = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return v
    return default


MODEL = _pop_opt("--model", DEFAULT_MODEL)
TAG = re.sub(r"[^\w.-]+", "_", MODEL)
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def log_name(kind, seed):
    """Old names for the default model (keeps earlier logs comparable), model tag otherwise."""
    return f"{kind}_log_s{seed}.jsonl" if MODEL == DEFAULT_MODEL else f"{kind}_{TAG}_s{seed}.jsonl"
API = "http://localhost:11434"


def post(path, body, timeout=600):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def gpu_used():
    out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used",
                                   "--format=csv,noheader,nounits"], text=True)
    return int(out.strip().splitlines()[0])


def unload():
    post("/api/generate", {"model": MODEL, "keep_alive": 0})
    time.sleep(3)


ctxs = [int(x) for x in sys.argv[1:]] or [4096, 8192, 16384, 32768]
results = []
base = gpu_used()
print(f"baseline VRAM used: {base} MiB")
for ctx in ctxs:
    unload()
    t = time.time()
    r = post("/api/generate", {
        "model": MODEL, "prompt": "Write two sentences about the sea.",
        "think": False, "stream": False, "keep_alive": "5m",
        "options": {"num_ctx": ctx, "num_predict": 64, "temperature": 0},
    })
    load_s = time.time() - t
    ps = json.loads(urllib.request.urlopen(API + "/api/ps").read())
    m = next(x for x in ps["models"] if x["name"] == MODEL)
    size, vram = m["size"], m["size_vram"]
    tps = r["eval_count"] / (r["eval_duration"] / 1e9)
    print(f"ctx={ctx:>6}  total={size/2**30:.2f}GiB  on_gpu={vram/2**30:.2f}GiB "
          f"({100*vram/size:.0f}% GPU)  nvidia-smi={gpu_used()} MiB  "
          f"gen={tps:.1f} tok/s  load+gen={load_s:.0f}s", flush=True)
    results.append({"num_ctx": ctx, "size_gib": round(size / 2**30, 2), "gpu_pct": round(100 * vram / size),
                    "tok_s": round(tps, 1), "load_s": round(load_s)})
unload()
os.makedirs(LOG_DIR, exist_ok=True)
json.dump({"model": MODEL, "results": results}, open(os.path.join(LOG_DIR, f"vram_{TAG}.json"), "w"), indent=1)
