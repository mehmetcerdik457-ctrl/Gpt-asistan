"""No network and no real purchases: voided order safe-audit regressions."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
import urllib.parse
import urllib.error
from server.play_voided_audit import (
    VoidedOrderAuditor, VoidedAuditUnavailable, initialize_voided_orders)
from server.play_google_api import PACKAGE

NOW = 1794600000

def order(*, order_id="GPA.1111-2222-3333-44444..0", token="play-renewal-token",
          voided="1794500000000", reason=7):
    return {"kind":"androidpublisher#voidedPurchase",
            "orderId":order_id,"purchaseToken":token,
            "voidedTimeMillis":voided,"voidedReason":reason}

class FakeResponse:
    status = 200
    def __init__(self, data): self.data=data
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return json.dumps(self.data).encode()[:n]

class FakePages:
    def __init__(self,*pages):
        self.pages=list(pages)
        self.requests=[]
    def __call__(self,request,timeout):
        assert timeout == 8
        self.requests.append(request)
        if not self.pages: raise AssertionError("UNEXPECTED_NETWORK")
        page=self.pages.pop(0)
        if isinstance(page,BaseException): raise page
        return FakeResponse(page)

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbpath=self.tmp.name+"/audit.sqlite3"
        with sqlite3.connect(self.dbpath) as db:
            initialize_voided_orders(db)
        self.calls=0
    def make(self,pages=None,enabled=True,oauth="synthetic-token"):
        pages=pages or FakePages({"voidedPurchases":[order()]})
        def supplier():
            self.calls+=1
            return oauth
        return VoidedOrderAuditor(oauth_supplier=supplier,
            db_factory=lambda:sqlite3.connect(self.dbpath),
            enabled=lambda:enabled,opener=pages,clock=lambda:NOW), pages
    def rows(self):
        with sqlite3.connect(self.dbpath) as db:
            return db.execute(
                "SELECT order_sha256,purchase_token_sha256,reason "
                "FROM play_voided_orders_audit").fetchall()
    def test_bounded_type_one_query_and_never_purchase_write(self):
        svc,api=self.make()
        result=svc.reconcile()
        self.assertEqual(result,{"pages":1,"observed_orders":1,"new_orders":1,
                                 "entitlement_changed":False})
        req=api.requests[0]
        self.assertEqual(req.get_method(),"GET")
        self.assertEqual(req.get_header("Authorization"),"Bearer synthetic-token")
        self.assertIn("/applications/"+PACKAGE+"/purchases/voidedpurchases?",req.full_url)
        params=urllib.parse.parse_qs(urllib.parse.urlsplit(req.full_url).query)
        self.assertEqual(params["type"],["1"])
        self.assertEqual(params["maxResults"],["1000"])
        self.assertNotIn("access_token",params)
        self.assertNotIn("purchaseToken",params)
    def test_hashed_order_and_purchase_only(self):
        svc,api=self.make()
        svc.reconcile()
        self.assertEqual(self.rows(),[(
            hashlib.sha256(b"GPA.1111-2222-3333-44444..0").hexdigest(),
            hashlib.sha256(b"play-renewal-token").hexdigest(),7)])
    def test_repeated_window_idempotent(self):
        svc,_=self.make()
        self.assertEqual(svc.reconcile()["new_orders"],1)
        svc2,_=self.make()
        self.assertEqual(svc2.reconcile()["new_orders"],0)
        self.assertEqual(len(self.rows()),1)
    def test_distinct_renewal_orders_share_token_but_not_order_id(self):
        api=FakePages({"voidedPurchases":[order(order_id="GPA.1"),
                      order(order_id="GPA.2")]})
        svc,_=self.make(api)
        self.assertEqual(svc.reconcile()["new_orders"],2)
        rows=self.rows()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0][1],rows[1][1])
    def test_pagination_returns_all_rows(self):
        api=FakePages({"voidedPurchases":[order(order_id="GPA.1")],
                       "tokenPagination":{"nextPageToken":"p2"}},
                      {"voidedPurchases":[order(order_id="GPA.2")]})
        svc,_=self.make(api)
        out=svc.reconcile()
        self.assertEqual((out["pages"],out["new_orders"]),(2,2))
        second=urllib.parse.parse_qs(urllib.parse.urlsplit(api.requests[1].full_url).query)
        self.assertEqual(second["token"],["p2"])
    def test_more_than_five_pages_rolls_back(self):
        api=FakePages(*[{"voidedPurchases":[order(order_id="GPA."+str(i))],
                         "tokenPagination":{"nextPageToken":"p"+str(i+1)}}
                        for i in range(5)])
        svc,_=self.make(api)
        with self.assertRaisesRegex(VoidedAuditUnavailable,"PAGINATION_LIMIT"):
            svc.reconcile()
        self.assertEqual(self.rows(),[])
    def test_pagination_cycle_rolls_back(self):
        api=FakePages({"voidedPurchases":[order()],"tokenPagination":{"nextPageToken":"same"}},
                      {"voidedPurchases":[],"tokenPagination":{"nextPageToken":"same"}})
        svc,_=self.make(api)
        with self.assertRaisesRegex(VoidedAuditUnavailable,"PAGINATION_CYCLE"):
            svc.reconcile()
        self.assertEqual(self.rows(),[])
    def test_api_outage_rolls_back_without_secrets(self):
        api=FakePages({"voidedPurchases":[order()],"tokenPagination":{"nextPageToken":"two"}},
                      urllib.error.URLError("SECRET_ENDPOINT"))
        svc,_=self.make(api)
        with self.assertRaises(VoidedAuditUnavailable) as e: svc.reconcile()
        self.assertNotIn("SECRET_ENDPOINT",str(e.exception))
        self.assertEqual(self.rows(),[])
    def test_conflicting_order_across_pages_denied(self):
        api=FakePages({"voidedPurchases":[order()],"tokenPagination":{"nextPageToken":"two"}},
                      {"voidedPurchases":[order(token="different-token")]})
        svc,_=self.make(api)
        with self.assertRaisesRegex(VoidedAuditUnavailable,"ORDER_CONFLICT"):
            svc.reconcile()
        self.assertEqual(self.rows(),[])
    def test_conflicting_existing_order_rejected(self):
        self.make()[0].reconcile()
        api=FakePages({"voidedPurchases":[order(token="modified-renewal-token")]})
        svc,_=self.make(api)
        with self.assertRaisesRegex(VoidedAuditUnavailable,"ORDER_CONFLICT"):
            svc.reconcile()
        self.assertEqual(len(self.rows()),1)
    def test_disabled_blocks_before_oauth_and_google(self):
        svc,api=self.make(FakePages(),enabled=False)
        with self.assertRaisesRegex(VoidedAuditUnavailable,"DISABLED"):
            svc.reconcile()
        self.assertEqual(self.calls,0)
        self.assertEqual(api.requests,[])
    def test_bad_credential_denied(self):
        for tok in ("", "abc\r\nInjected: bad", "bad token"):
            svc,api=self.make(FakePages(),oauth=tok)
            with self.subTest(token=tok), self.assertRaises(VoidedAuditUnavailable):
                svc.reconcile()
            self.assertEqual(api.requests,[])
    def test_missing_order_id_refused(self):
        item=order()
        del item["orderId"]
        svc,_=self.make(FakePages({"voidedPurchases":[item]}))
        with self.assertRaisesRegex(VoidedAuditUnavailable,"RECORD_INVALID"):
            svc.reconcile()
    def test_bad_purchase_token_denied(self):
        svc,_=self.make(FakePages({"voidedPurchases":[order(token="bad/token")]}))
        with self.assertRaises(VoidedAuditUnavailable): svc.reconcile()
        self.assertEqual(self.rows(),[])
    def test_boolean_reason_rejected(self):
        svc,_=self.make(FakePages({"voidedPurchases":[order(reason=True)]}))
        with self.assertRaises(VoidedAuditUnavailable): svc.reconcile()
    def test_out_of_range_reason_rejected(self):
        svc,_=self.make(FakePages({"voidedPurchases":[order(reason=99)]}))
        with self.assertRaises(VoidedAuditUnavailable): svc.reconcile()
    def test_untrusted_200_json_rejected(self):
        svc,_=self.make(FakePages({"error":"not-authorized"}))
        with self.assertRaisesRegex(VoidedAuditUnavailable,"RESPONSE_INVALID"):
            svc.reconcile()
        self.assertEqual(self.rows(),[])
    def test_empty_page_valid(self):
        svc,_=self.make(FakePages({"voidedPurchases":[]}))
        self.assertEqual(svc.reconcile()["observed_orders"],0)
        self.assertEqual(self.rows(),[])
    def test_invalid_window_denied_without_api(self):
        bad=[dict(start_ms=NOW*1000,end_ms=NOW*1000),
             dict(start_ms=1,end_ms=2),
             dict(start_ms=True,end_ms=NOW*1000)]
        for options in bad:
            svc,api=self.make(FakePages())
            with self.subTest(options=options), self.assertRaises(VoidedAuditUnavailable):
                svc.reconcile(**options)
            self.assertEqual(api.requests,[])
    def test_missing_ledger_migration_is_not_silently_created(self):
        svc,_=self.make()
        svc._db_factory=lambda:sqlite3.connect(":memory:")
        with self.assertRaises(VoidedAuditUnavailable): svc.reconcile()
        self.assertEqual(self.rows(),[])
    def test_never_modifies_subscription_owner_binding(self):
        with sqlite3.connect(self.dbpath) as db:
            db.execute("CREATE TABLE play_token_owners (token_sha256 TEXT PRIMARY KEY,owner_id TEXT)")
            db.execute("INSERT INTO play_token_owners VALUES ('digest','owner')")
        self.make()[0].reconcile()
        with sqlite3.connect(self.dbpath) as db:
            self.assertEqual(db.execute("SELECT * FROM play_token_owners").fetchall(),
                             [("digest","owner")])

if __name__=="__main__": unittest.main()
