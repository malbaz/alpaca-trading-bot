"""Offline session and order tests: never connect to Alpaca."""
import ast
import hashlib
import logging
import unittest
import uuid
from typing import Dict, Any
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

def load_class(file, name, methods, scope):
    tree = ast.parse((ROOT / file).read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in methods]
    exec(compile(ast.Module(body=[cls], type_ignores=[]), file, 'exec'), scope)
    return scope[name]

class SessionTests(unittest.TestCase):
    def phase(self, day, hour, minute=0, holiday=False, early=False):
        stamp = datetime(2026, 11, day, hour, minute, tzinfo=ZoneInfo('America/New_York'))
        calls = []
        def calendar(req):
            calls.append(req)
            return [] if holiday else [NS(open=stamp.replace(hour=9, minute=30), close=stamp.replace(hour=13 if early else 16, minute=0))]
        scope = dict(datetime=datetime, ZoneInfo=ZoneInfo, GetCalendarRequest=lambda **kw: NS(**kw),
                     trading=NS(get_clock=lambda: NS(timestamp=stamp, is_open=False), get_calendar=calendar),
                     log=logging.getLogger('test'), _sell_calendar_cache={})
        tree = ast.parse((ROOT / 'broker.py').read_text())
        node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sell_market_phase'), None)
        self.assertIsNotNone(node, 'sell-specific session clock missing')
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'broker.py', 'exec'), scope)
        return scope['sell_market_phase']()
    def test_pre_open(self): self.assertEqual(self.phase(10, 5), 'EXTENDED')
    def test_regular(self): self.assertEqual(self.phase(10, 10), 'REGULAR')
    def test_post_close(self): self.assertEqual(self.phase(10, 18), 'EXTENDED')
    def test_friday_post_close(self): self.assertEqual(self.phase(13, 18), 'EXTENDED')
    def test_no_overnight(self): self.assertEqual(self.phase(10, 20), 'CLOSED')
    def test_no_before_four(self): self.assertEqual(self.phase(10, 3), 'CLOSED')
    def test_weekend(self): self.assertEqual(self.phase(14, 10), 'CLOSED')
    def test_holiday(self): self.assertEqual(self.phase(26, 10, holiday=True), 'CLOSED')
    def test_half_day_no_postmarket(self): self.assertEqual(self.phase(27, 14, early=True), 'CLOSED')

class OrderTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(state='OPEN', qty=4, entry_price=2, stop=1.8)
        self.calls = []
        self.pending = []
        self.available = 4
        self.quote = NS(bid_price=2.06, ask_price=2.07, timestamp=datetime.now(timezone.utc))
        self.position = NS(symbol='PCT', qty='4', qty_available='4', current_price='2.06')
        def upsert(sym, **kw): self.row.update(kw)
        self.client = NS(get_orders=lambda req: self.pending, cancel_order_by_id=lambda oid:self.calls.append(('cancel',oid)),
                         get_all_positions=lambda:[self.position], get_open_position=lambda sym:NS(qty='4',qty_available=str(self.available)),
                         close_position=lambda sym:self.calls.append(('market',sym)), submit_order=lambda req:self.calls.append(('limit',req)))
        scope = dict(Dict=Dict, Any=Any, uuid=uuid, state=NS(get=lambda sym:self.row, upsert=upsert, clear=lambda sym:self.row.clear()),
                     broker=NS(snapshots=lambda syms:{'PCT':NS(latest_quote=self.quote)}), strategy=NS(spread_pct=lambda b,a:(a-b)/((a+b)/2)*100),
                     settings=NS(max_spread_exit_pct=1.0), datetime=datetime, timezone=timezone,
                     time=NS(time=lambda:1, sleep=lambda n:None), log=logging.getLogger('test'),
                     GetOrdersRequest=lambda **kw:NS(**kw), LimitOrderRequest=lambda **kw:NS(**kw),
                     OrderSide=NS(SELL='sell'), TimeInForce=NS(DAY='day'), QueryOrderStatus=NS(OPEN='open'))
        cls=load_class('order_manager.py','OrderManager',('__init__','sell'),scope)
        self.manager=cls(self.client,None)
    def test_extended_limit_uses_bid_without_discount(self):
        result=self.manager.sell('PCT','وقف خسارة',ref_price=2.065,phase='EXTENDED')
        self.assertEqual(result['status'],'submitted')
        req=self.calls[-1][1]
        self.assertEqual(req.limit_price,2.06)
        self.assertTrue(req.extended_hours)
        self.assertEqual(req.time_in_force,'day')
        self.assertEqual(req.qty,4)
    def test_regular_market_sale(self):
        self.assertEqual(self.manager.sell('PCT','وقف',phase='REGULAR')['status'],'submitted')
        self.assertEqual(self.calls,[('market','PCT')])
    def test_closed_does_not_cancel_or_sell(self):
        self.assertEqual(self.manager.sell('PCT','وقف',phase='CLOSED')['status'],'rejected')
        self.assertEqual(self.calls,[])
    def test_stale_quote_keeps_protection(self):
        self.quote.timestamp=datetime(2020,1,1,tzinfo=timezone.utc)
        self.assertEqual(self.manager.sell('PCT','وقف',phase='EXTENDED')['status'],'rejected')
        self.assertEqual(self.calls,[])
    def test_wide_spread_keeps_protection(self):
        self.quote.ask_price=2.31
        self.assertEqual(self.manager.sell('PCT','وقف',phase='EXTENDED')['status'],'rejected')
        self.assertEqual(self.calls,[])
    def test_no_sale_before_shares_released(self):
        self.available=0
        self.assertEqual(self.manager.sell('PCT','وقف',phase='EXTENDED')['status'],'rejected')
        self.assertEqual(self.calls,[])
    def test_pending_sale_not_duplicated(self):
        self.row['state']='PENDING_SELL'
        self.assertEqual(self.manager.sell('PCT','وقف',phase='EXTENDED')['status'],'rejected')
        self.assertEqual(self.calls,[])

class BuyAndFlowTests(unittest.TestCase):
    def test_buy_method_is_unchanged(self):
        tree = ast.parse((ROOT / 'order_manager.py').read_text())
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'buy')
        self.assertEqual(hashlib.sha256(ast.dump(node).encode()).hexdigest(), '29fe6cbeebcf3088a5a3fe949bcb69544b8777b3f8c269788df604ec79b7a47f')
    def test_original_buy_clock_unchanged(self):
        tree = ast.parse((ROOT / 'broker.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'market_phase')
        self.assertEqual(hashlib.sha256(ast.dump(node).encode()).hexdigest(), '0ad64cebb6c242567c202fdf8de50fff83a751cb5565d17bcefc8253fbacd36c')
    def test_engine_friday_sell_does_not_enable_buy(self):
        observations=[]
        scope=dict(settings=NS(watchlist=[]), state=NS(active=lambda:[]),
                   broker=NS(market_phase=lambda:'CLOSED',sell_market_phase=lambda:'EXTENDED',snapshots=lambda symbols:{}))
        cls=load_class('engine.py','Engine',('__init__','tick'),scope)
        engine=cls(NS(sync_existing_stops=lambda:True,reconcile=lambda:None,cancel_stale_entries=lambda:None))
        engine.refresh_universe=lambda:observations.append('refresh')
        engine.manage_exits=lambda phase,snaps:observations.append(('sell',phase))
        engine.scan=lambda *args:observations.append('buy')
        self.assertEqual(engine.tick(),'EXTENDED')
        self.assertEqual(observations,[('sell','EXTENDED')])

if __name__ == '__main__': unittest.main()
