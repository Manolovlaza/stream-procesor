import os, subprocess, json, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed

stream_url = os.environ.get("STREAM_URL", "https://kick.com/davooxeneize/videos/7a39ebc9-bae0-4dad-80e2-29439a6f0989")
api_url = os.environ.get("API_URL", "https://new-api.stiflercr7.qzz.io/v1/audio/transcriptions")
api_key = os.environ.get("API_KEY", "opencode")

print(f"🚀 Iniciando procesamiento para: {stream_url}")

# 1. Descarga ultra-rápida de audio nativo con yt-dlp (-N 16, 0.00s de recodificación)
print("📥 1. Descargando pista de audio nativa a 1 Gbps...")
cmd_dl = ["yt-dlp", "-N", "16", "-f", "worst", "-x", "--audio-format", "copy", stream_url, "-o", "full_audio.m4a"]
res_dl = subprocess.run(cmd_dl, capture_output=True, text=True)

if not os.path.exists("full_audio.m4a"):
    print("❌ Error descargando audio con yt-dlp:", res_dl.stderr)
    exit(1)

file_size_mb = os.path.getsize("full_audio.m4a") / (1024 * 1024)
print(f"✅ Audio descargado exitosamente: {file_size_mb:.2f} MB")

# 2. Troceado instantáneo en bloques de 45 minutos con FFmpeg
print("✂️ 2. Troceando audio en bloques de 45 minutos con FFmpeg...")
cmd_split = ["ffmpeg", "-i", "full_audio.m4a", "-f", "segment", "-segment_time", "2700", "-c", "copy", "chunk_%02d.m4a"]
subprocess.run(cmd_split, capture_output=True)

chunks = sorted([f for f in os.listdir(".") if f.startswith("chunk_") and f.endswith(".m4a")])
print(f"📦 Creados {len(chunks)} bloques de audio para transcripción paralela.")

# 3. Transcripción en paralelo usando el pool de Cloudflare
print("⚡ 3. Enviando bloques en paralelo a New-API (Pool de Cloudflare)...")
headers = {"Authorization": f"Bearer {api_key}"}

def transcribe_chunk(chunk_file, idx):
    offset = idx * 2700.0
    with open(chunk_file, "rb") as f:
        files = {"file": (chunk_file, f, "audio/m4a")}
        data = {"model": "whisper-large-v3-turbo", "response_format": "verbose_json"}
        t0 = time.time()
        resp = requests.post(api_url, headers=headers, files=files, data=data, timeout=300)
        elapsed = time.time() - t0

    if resp.status_code == 200:
        res = resp.json()
        segments = res.get("segments", [])
        print(f"  • Bloque {idx:02d} ({chunk_file}): HTTP 200 OK en {elapsed:.2f}s ({len(segments)} subtítulos)")
        return idx, segments
    else:
        print(f"  • Bloque {idx:02d} ({chunk_file}): ERROR HTTP {resp.status_code}")
        return idx, []

start_t = time.time()
results = {}
with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
    futures = [executor.submit(transcribe_chunk, ch, i) for i, ch in enumerate(chunks)]
    for fut in as_completed(futures):
        idx, segs = fut.result()
        results[idx] = segs

total_t = time.time() - start_t
print(f"\n🎉 TODAS LAS TRANSCRIPCIONES EN PARALELO COMPLETADAS EN {total_t:.2f} SEGUNDOS!")

# 4. Generación del archivo Master SRT final
def format_ts(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

srt_lines = []
total_b = 0
for idx in sorted(results.keys()):
    offset = idx * 2700.0
    for seg in results[idx]:
        total_b += 1
        st = format_ts(seg.get("start", 0) + offset)
        et = format_ts(seg.get("end", 0) + offset)
        txt = seg.get("text", "").strip()
        if txt:
            srt_lines.append(f"{total_b}\n{st} --> {et}\n{txt}\n")

with open("MASTER_SUBTITLES.srt", "w", encoding="utf-8") as f:
    f.write("\n".join(srt_lines))

print(f"📄 Subtítulos Maestro generados con {total_b} bloques de tiempo sincronizados.")
