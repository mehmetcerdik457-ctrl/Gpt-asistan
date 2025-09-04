import subprocess, os, json, wave, math
try:
    import vosk
except Exception:
    vosk=None

def speak(text:str, lang:str="tr"):
    # Termux'ta espeak-ng ile seslendir
    text = text.strip() or "Boş metin."
    lang = lang or "tr"
    try:
        subprocess.run(["espeak-ng","-v",lang, text], check=False)
        return True
    except Exception:
        return False

def trans_offline(text:str, lang:str="en"):
    # Hafif, çevrimdışı "oyuncak" çeviri sözlüğü (gerektiğinde genişletilir)
    table = {
        ("tr","en"): {"merhaba":"hello","dünya":"world","nasılsın":"how are you"},
        ("en","tr"): {"hello":"merhaba","world":"dünya","thanks":"teşekkürler"},
        ("tr","ar"): {"merhaba":"مرحبا","dünya":"العالم"},
        ("ar","tr"): {"مرحبا":"merhaba","العالم":"dünya"},
    }
    src="auto"
    # çok basit tespit
    if any("\u0600" <= ch <= "\u06FF" for ch in text): src="ar"
    elif any('a'<=ch.lower()<='z' for ch in text): src="en"
    else: src="tr"
    tgt = (lang or "en").lower()
    mp = table.get((src,tgt), {})
    out = " ".join(mp.get(w.lower(), w) for w in text.split())
    return out

def stt_wav_local(path:str, lang:str="tr"):
    if not vosk: return {"ok":False,"error":"vosk yok"}
    model_dir = os.path.expanduser(os.getenv("VOSK_TR_MODEL","~/models/vosk/tr-small"))
    if not os.path.isdir(model_dir):
        return {"ok":False,"error":"model yok"}
    try:
        rec_model = vosk.Model(model_dir)
        wf = wave.open(path, "rb")
        if wf.getnchannels()!=1 or wf.getsampwidth()!=2 or wf.getframerate()!=16000:
            return {"ok":False,"error":"wav 16kHz/mono/16bit olmalı"}
        rec = vosk.KaldiRecognizer(rec_model, wf.getframerate())
        txt=[]
        while True:
            data = wf.readframes(4000)
            if len(data)==0: break
            if rec.AcceptWaveform(data):
                res=json.loads(rec.Result()); txt.append(res.get("text",""))
        res=json.loads(rec.FinalResult()); txt.append(res.get("text",""))
        full=" ".join([t for t in txt if t]).strip()
        return {"ok":True,"text":full}
    except Exception as e:
        return {"ok":False,"error":str(e)}

def add_cron_reminder(when_cron:str, message:str):
    # when_cron: "30 9 * * *" gibi; message: bildirim metni
    # termux-notification için termux-api app gerekir.
    import subprocess, tempfile
    line=f'{when_cron} termux-notification --title "Hatırlatma" --content "{message}"\n'
    try:
        cur=subprocess.run(["crontab","-l"], capture_output=True, text=True).stdout
    except Exception:
        cur=""
    if line not in cur:
        new = cur + line
        p=tempfile.NamedTemporaryFile(delete=False)
        p.write(new.encode("utf-8")); p.flush(); p.close()
        subprocess.run(["crontab", p.name], check=False)
    return True
