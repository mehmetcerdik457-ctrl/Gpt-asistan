"""Read-only doctor; no automatic repair."""
import importlib.util, shutil, sys, json
TOOLS=("git","python","pytest","ruff","yt-dlp","ffmpeg","ffprobe")
MODULES=("PIL","cv2","faster_whisper","librosa")
def diagnose():
 return {"python":sys.version.split()[0],"tools":{x:shutil.which(x) for x in TOOLS},"modules":{x:importlib.util.find_spec(x) is not None for x in MODULES},"repair_mode":"disabled"}
if __name__=="__main__": print(json.dumps(diagnose(),indent=2))
