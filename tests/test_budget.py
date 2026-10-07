from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from api_budget import ApiBudget, BudgetExhausted


class BudgetTests(unittest.TestCase):
    def test_background_and_foreground_share_one_atomic_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = ApiBudget(Path(directory) / 'budget.json')
            def attempt(_):
                try:
                    budget.consume()
                    return True
                except BudgetExhausted:
                    return False
            with ThreadPoolExecutor(max_workers=8) as workers:
                self.assertEqual(sum(workers.map(attempt, range(40))), 10)
            restored = ApiBudget(budget.path)
            self.assertEqual(restored.used, 10)
            self.assertEqual(restored.credit, 0)

    def test_credit_survives_restart_and_only_grows_during_active_use(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'budget.json'
            with patch('api_budget.time.monotonic', return_value=0):
                budget = ApiBudget(path)
                for _ in range(10):
                    budget.consume()
                with self.assertRaises(BudgetExhausted):
                    budget.consume()
                restarted = ApiBudget(path)
                self.assertFalse(restarted.available())
                restarted.tick(False, 30)
                self.assertEqual(restarted.credit, 0)
                restarted.tick(True, 30)
                for now in range(40, 3631, 10):
                    restarted.tick(True, now)
                self.assertAlmostEqual(restarted.credit, 5)

    def test_total_cap_and_corrupt_state_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'budget.json'
            path.write_text('{"credit": 10, "used": 2000}')
            self.assertFalse(ApiBudget(path).available())
            path.write_text('not valid JSON')
            self.assertFalse(ApiBudget(path).available())

    def test_resume_from_sleep_does_not_refill_credit(self):
        with tempfile.TemporaryDirectory() as directory, patch('api_budget.time.monotonic', return_value=0):
            budget = ApiBudget(Path(directory) / 'budget.json')
            budget.credit = 0
            budget.tick(True, 0)
            budget.tick(True, 36000)
            self.assertLess(budget.credit, 0.05)
