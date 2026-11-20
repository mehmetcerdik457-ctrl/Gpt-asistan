"""yt-dlp metadata and subtitle adapter. User-invoked only."""
import json, shutil, subprocess
from urllib.parse import urlparse
def valid_url(value):
 p=urlparse(value)
 if p.scheme not in ("https","http") or not p.netloc: raise ValueError("http(s) URL required")
 return value
def metadata(url):
 exe=shutil.which("yt-dlp")
 if not exe: return {"status":"TOOL_MISSING","required":"yt-dlp"}
 p=subprocess.run([exe,"--dump-single-json","--skip-download",valid_url(url)],capture_output=True,text=True,timeout=90,check=False)
 if p.returncode: return {"status":"ERROR","stderr":p.stderr[-2000:]}
 d=json.loads(p.stdout)
 return {k:d.get(k) for k in ("id","title","channel","duration","upload_date")}|{"status":"OK","subtitle_languages":sorted(d.get("subtitles",{})),"auto_caption_languages":sorted(d.get("automatic_captions",{}))}
def subtitles(url,output_dir="artifacts/subtitles",languages="tr,en"):
 exe=shutil.which("yt-dlp")
 if not exe: return {"status":"TOOL_MISSING","required":"yt-dlp"}
 from pathlib import Path
 out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
 p=subprocess.run([exe,"--skip-download","--write-subs","--write-auto-subs","--sub-langs",languages,"--sub-format","vtt","-o",str(out/"%(id)s.%(ext)s"),valid_url(url)],capture_output=True,text=True,timeout=180,check=False)
 return {"status":"OK" if p.returncode==0 else "ERROR","output_dir":str(out),"stderr":p.stderr[-2000:]}
