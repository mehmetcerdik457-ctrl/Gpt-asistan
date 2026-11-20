import asyncio,pytest
from worker_fleet.registry import WORKERS,dispatch,fleet_status
def test_50_slots(): assert len(WORKERS)==50 and len(set(w.id for w in WORKERS))==50
def test_live_models_not_fabricated(): assert fleet_status()["live_model_workers"]==0
def test_dispatch_explicitly_marks_missing_adapters():
 r=asyncio.run(dispatch(["worker-01","worker-02"],2)); assert all(x["result"]["status"]=="NOT_CONFIGURED" for x in r)
def test_concurrency_limit():
 with pytest.raises(ValueError): asyncio.run(dispatch(["worker-01"],9))
