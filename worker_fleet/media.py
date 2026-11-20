"""FFprobe inspection and scene manifest validation."""
import json, shutil, subprocess
from pathlib import Path
def probe(path):
 exe=shutil.which("ffprobe")
 if not exe: return {"status":"TOOL_MISSING","required":"ffprobe"}
 p=subprocess.run([exe,"-v","error","-show_format","-show_streams","-of","json",path],capture_output=True,text=True,timeout=60,check=False)
 return {"status":"OK","metadata":json.loads(p.stdout)} if p.returncode==0 else {"status":"ERROR","stderr":p.stderr[-2000:]}
def validate_scene_manifest(path):
 data=json.loads(Path(path).read_text(encoding="utf-8"))
 if not isinstance(data,dict) or not isinstance(data.get("scenes"),list): raise ValueError("scenes array required")
 for i,s in enumerate(data["scenes"]):
  if not isinstance(s,dict) or not isinstance(s.get("asset"),str): raise ValueError("scene asset missing: %d"%i)
  p=Path(s["asset"])
  if p.is_absolute() or ".." in p.parts: raise ValueError("scene asset path traversal denied")
 return {"status":"OK","scenes":len(data["scenes"])}
