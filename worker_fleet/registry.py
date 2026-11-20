"""KRAL worker registry: 50 deterministic local slots, not autonomous LLM agents."""
import asyncio
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class Worker:
    id: str
    group: str
    role: str

GROUPS = {
"github":["repo_inventory","pr_triage","issue_triage","branch_audit","release_audit"],
"drive_owner":["drive_index","owner_policy","secret_hygiene","access_review","evidence_ledger"],
"coding":["python_build","android_build","module_scaffold","dependency_audit","refactor_check","api_contract","migration_check","code_search","lint","type_check"],
"analysis_test":["test_unit","test_integration","test_regression","static_security","coverage","benchmark","log_analysis","failure_triage","doctor","reporting"],
"youtube":["youtube_metadata","youtube_download","youtube_subtitles","youtube_transcript","youtube_chapters"],
"media":["audio_probe","audio_convert","audio_cleanup","video_probe","video_transcode","video_trim","image_process","thumbnail","subtitle_sync","media_qc"],
"studio_automation":["scene_manifest","timeline","render_queue","asset_catalog","studio_export"]}
WORKERS=tuple(Worker("worker-%02d"%(i+1),g,r) for i,(g,roles) in enumerate((g,role) for g,roles in GROUPS.items() for role in roles))
assert len(WORKERS)==50
async def run_worker(worker_id,payload=None):
    w=next((x for x in WORKERS if x.id==worker_id),None)
    if w is None: raise KeyError(worker_id)
    return {"worker":asdict(w),"result":{"status":"NOT_CONFIGURED","detail":"Adapter not configured; no external action or model call performed."}}
async def dispatch(worker_ids,concurrency=4):
    if not 1<=concurrency<=8: raise ValueError("concurrency must be between 1 and 8")
    sem=asyncio.Semaphore(concurrency)
    async def bounded(wid):
        async with sem: return await run_worker(wid)
    return await asyncio.gather(*(bounded(wid) for wid in worker_ids))
def fleet_status():
    return {"registered_slots":len(WORKERS),"groups":{g:sum(w.group==g for w in WORKERS) for g in GROUPS},"live_model_workers":0,"execution_mode":"local_handler_only"}
