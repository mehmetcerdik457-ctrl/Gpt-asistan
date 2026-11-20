#!/usr/bin/env python3
"""End-to-end YouTube -> audio/transcript -> scenes -> verified JSON manifest."""
import argparse, hashlib, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from worker_fleet.youtube import metadata as get_metadata, subtitles as get_subtitles, valid_url

def run(cmd, timeout=900):
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    if p.returncode: raise RuntimeError(f"command failed ({p.returncode}): {' '.join(cmd[:5])}\n{p.stderr[-3000:]}")
    return p

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--url",default=os.getenv("STUDIO_SOURCE_URL","https://www.youtube.com/watch?v=BaW_jenozKc"))
    ap.add_argument("--output",default=os.getenv("STUDIO_OUTPUT_DIR","artifacts/studio"))
    ap.add_argument("--whisper-model",default=os.getenv("WHISPER_MODEL","tiny"))
    ap.add_argument("--skip-transcription",action="store_true")
    a=ap.parse_args(); url=valid_url(a.url); out=Path(a.output).resolve()
    for d in ("video","audio","subtitles","scenes","transcript"): (out/d).mkdir(parents=True,exist_ok=True)
    meta=get_metadata(url)
    if meta.get("status")!="OK": raise RuntimeError(f"metadata failed: {meta}")
    (out/"metadata.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    sub=get_subtitles(url,str(out/"subtitles"),"tr,en")
    video=out/"video"/"source.mp4"
    run(["yt-dlp","--no-playlist","--no-warnings","-f","bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b","--merge-output-format","mp4","-o",str(video),url],1200)
    if not video.exists():
        candidates=sorted((out/"video").glob("source.*"))
        if not candidates: raise RuntimeError("yt-dlp produced no video file")
        video=candidates[0]
    audio=out/"audio"/"audio.wav"
    run(["ffmpeg","-y","-i",str(video),"-vn","-ac","1","-ar","16000","-c:a","pcm_s16le",str(audio)])
    pattern=str(out/"scenes"/"scene-%03d.jpg")
    run(["ffmpeg","-y","-i",str(video),"-vf","select='gt(scene,0.30)',scale='min(1280,iw)':-2","-vsync","vfr","-frames:v","24",pattern])
    scenes=sorted((out/"scenes").glob("scene-*.jpg"))
    if not scenes:
        fallback=out/"scenes"/"scene-001.jpg"
        run(["ffmpeg","-y","-ss","0","-i",str(video),"-frames:v","1","-vf","scale='min(1280,iw)':-2",str(fallback)])
        scenes=[fallback]
    transcript_status="SKIPPED"
    if not a.skip_transcription:
        try:
            from faster_whisper import WhisperModel
            model=WhisperModel(a.whisper_model,device="cpu",compute_type="int8")
            segments,info=model.transcribe(str(audio),vad_filter=True)
            lines=[f"[{s.start:0.2f}-{s.end:0.2f}] {s.text.strip()}" for s in segments]
            (out/"transcript"/"transcript.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
            transcript_status="OK"
        except ImportError: transcript_status="UNAVAILABLE"
        except Exception as e:
            transcript_status="ERROR"; (out/"transcript"/"error.txt").write_text(str(e),encoding="utf-8")
    files=[]
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name!="manifest.json":
            files.append({"path":p.relative_to(out).as_posix(),"size_bytes":p.stat().st_size,"sha256":digest(p)})
    manifest={"schema_version":1,"status":"COMPLETED","created_at":datetime.now(timezone.utc).isoformat(),
      "source_url":url,"video":meta,"subtitle_status":sub.get("status"),
      "audio":{"path":"audio/audio.wav","status":"OK"},
      "transcription":{"status":transcript_status,"model":a.whisper_model},
      "scenes":[{"asset":p.relative_to(out).as_posix(),"sha256":digest(p)} for p in scenes],"files":files}
    for item in files:
        rel=Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts or not (out/rel).is_file(): raise RuntimeError(f"invalid manifest path: {rel}")
    for item in manifest["scenes"]:
        rel=Path(item["asset"])
        if rel.is_absolute() or ".." in rel.parts or not (out/rel).is_file(): raise RuntimeError(f"invalid scene path: {rel}")
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"status":"COMPLETED","manifest":str(out/"manifest.json"),"files":len(files),"scenes":len(scenes),"transcription":transcript_status}))
if __name__=="__main__":
    try: main()
    except Exception as e:
        print(json.dumps({"status":"FAILED","error":str(e)}),file=sys.stderr); raise
