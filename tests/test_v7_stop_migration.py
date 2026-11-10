"""Offline regression tests; no Alpaca connection or real orders."""
import ast
import logging
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace as NS


class SavedState:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE positions (symbol TEXT PRIMARY KEY, state TEXT, stop REAL, trailing INT, partial_done INT, bracket INT, entry_price REAL, qty REAL)')
        self.db.execute("INSERT INTO positions VALUES ('CLNE', 'OPEN', 1.82, 0, 0, 0, 1.915, 12)")

    def get(self, symbol):
        self.db.row_factory = sqlite3.Row
        row = self.db.execute('SELECT * FROM positions WHERE symbol=?', (symbol,)).fetchone()
        return dict(row) if row else None

    def upsert(self, symbol, **fields):
        for key, value in fields.items():
            self.db.execute(f'UPDATE positions SET {key}=? WHERE symbol=?', (value, symbol))
        self.db.commit()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'order_manager.py'
        tree = ast.parse(source.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('__init__', 'sync_existing_stops')]
        self.state = SavedState()
        from decimal import Decimal, ROUND_FLOOR
        scope = dict(state=self.state, log=logging.getLogger('test'), Decimal=Decimal,
                     ROUND_FLOOR=ROUND_FLOOR, GetOrdersRequest=lambda **kw: NS(**kw),
                     ReplaceOrderRequest=lambda **kw: NS(**kw),
                     QueryOrderStatus=NS(OPEN='open'), OrderSide=NS(SELL='sell'))
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), 'exec'), scope)
        self.orders = []
        self.calls = []
        self.client = NS(get_all_positions=lambda: [NS(symbol='CLNE', qty='12', avg_entry_price='1.915')],
                         get_orders=lambda req: self.orders, replace_order_by_id=self.replace)
        self.manager = scope['OrderManager'](self.client, None)

    def replace(self, oid, req):
        self.calls.append((oid, req.stop_price))
        return NS(id='new-stop')

    def test_old_saved_stop_becomes_ten_percent(self):
        self.assertTrue(self.manager.sync_existing_stops())
        self.assertEqual(self.state.get('CLNE')['stop'], 1.72)

    def test_trailing_profit_protection_is_preserved(self):
        self.state.upsert('CLNE', trailing=1, stop=2.10)
        self.manager.sync_existing_stops()
        self.assertEqual(self.state.get('CLNE')['stop'], 2.10)
        self.assertEqual(self.calls, [])

    def test_partial_profit_protection_is_preserved(self):
        self.state.upsert('CLNE', partial_done=1, stop=1.92)
        self.manager.sync_existing_stops()
        self.assertEqual(self.state.get('CLNE')['stop'], 1.92)

    def test_nested_bracket_stop_is_replaced_without_cancel(self):
        self.state.upsert('CLNE', bracket=1)
        self.orders = [NS(side='buy', stop_price=None, legs=[NS(id='old-stop', side='sell', stop_price='1.82', legs=[])])]
        self.manager.sync_existing_stops()
        self.assertEqual(self.calls, [('old-stop', 1.72)])
        self.assertEqual(self.state.get('CLNE')['stop'], 1.72)

    def test_failed_broker_replace_keeps_original_protection(self):
        self.orders = [NS(id='old-stop', side='sell', stop_price='1.82', legs=[])]
        def fail(*args):
            raise RuntimeError('broker unavailable')
        self.client.replace_order_by_id = fail
        self.assertFalse(self.manager.sync_existing_stops())
        self.assertEqual(self.state.get('CLNE')['stop'], 1.82)

    def test_missing_bracket_leg_uses_bot_stop_and_does_not_freeze(self):
        self.state.upsert('CLNE', bracket=1)
        self.assertTrue(self.manager.sync_existing_stops())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.state.get('CLNE')['stop'], 1.72)

    def test_broker_profit_stop_is_not_lowered(self):
        self.orders = [NS(id='profit-stop', side='sell', stop_price='2.10', legs=[])]
        self.manager.sync_existing_stops()
        self.assertEqual(self.calls, [])
        self.assertEqual(self.state.get('CLNE')['stop'], 1.82)

    def test_repeated_migration_does_not_change_stop(self):
        self.manager.sync_existing_stops()
        self.manager.sync_existing_stops()
        self.assertEqual(self.state.get('CLNE')['stop'], 1.72)

    def test_pending_sale_is_not_modified(self):
        self.state.upsert('CLNE', state='PENDING_SELL')
        self.manager.sync_existing_stops()
        self.assertEqual(self.state.get('CLNE')['stop'], 1.82)

    def test_pending_broker_replace_is_retried(self):
        self.orders = [NS(id='old-stop', side='sell', stop_price='1.82', legs=[])]
        self.client.replace_order_by_id = lambda *args: NS(status='pending_replace')
        self.assertFalse(self.manager.sync_existing_stops())
        self.assertEqual(self.state.get('CLNE')['stop'], 1.82)

    def test_engine_migrates_before_exits_and_only_once(self):
        path = Path(__file__).resolve().parents[1] / 'engine.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('__init__', 'tick')]
        observations = []
        scope = dict(settings=NS(watchlist=[]),
                     state=NS(active=lambda: [self.state.get('CLNE')]),
                     broker=NS(market_phase=lambda: 'REGULAR', snapshots=lambda symbols: {}))
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), scope)
        orders = NS(sync_existing_stops=self.manager.sync_existing_stops,
                    reconcile=lambda: None, cancel_stale_entries=lambda: None)
        engine = scope['Engine'](orders)
        engine.refresh_universe = lambda: None
        engine.manage_exits = lambda *args: observations.append(self.state.get('CLNE')['stop'])
        engine.scan = lambda *args: None
        engine.tick()
        self.assertEqual(observations, [1.72])
        self.state.upsert('CLNE', stop=2.10, trailing=1)
        engine.tick()
        self.assertEqual(observations, [1.72, 2.10])

    def test_engine_does_not_run_exits_after_failed_migration(self):
        path = Path(__file__).resolve().parents[1] / 'engine.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        cls.body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('__init__', 'tick')]
        scope = dict(settings=NS(watchlist=[]))
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), scope)
        engine = scope['Engine'](NS(sync_existing_stops=lambda: False))
        with self.assertRaises(RuntimeError):
            engine.tick()
        self.assertFalse(engine._stops_synced)


if __name__ == '__main__':
    unittest.main()
