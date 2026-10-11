import threading
import time
import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch
import main


class StartupTests(unittest.TestCase):
    def test_presence_does_not_wait_for_metadata_and_rejects_old_tab_result(self):
        release = threading.Event()
        entered = threading.Event()
        api = Mock(cache={}, disk_cache={})
        def slow_resolve(tab):
            entered.set()
            release.wait(3)
            return {'id': tab[2][0], 'name': tab[0]}, tab[2][2], {'id': tab[2][3], 'name': tab[1], 'elementType': 'ASSEMBLY'}
        api.resolve.side_effect = slow_resolve
        resolver = main.BackgroundResolver(api)
        first = ('Robot', 'Intake', ('doc', 'w', 'ws', 'a'))
        second = ('Robot', 'Shooter', ('doc', 'w', 'ws', 'b'))
        try:
            started = time.monotonic()
            document, context, element = resolver.resolve(first)
            self.assertLess(time.monotonic() - started, .5)
            self.assertTrue(entered.wait(1))
            payload = main.make_presence(document, element, first[1], 123, context)
            self.assertEqual(payload['state'], 'Document: Robot')
            self.assertTrue(main.presence_due(payload, None, 1, 0))
            future = resolver.pending[1]
            release.set()
            future.result(timeout=2)
            _, _, element = resolver.resolve(second)
            self.assertEqual(element['id'], 'b')
            self.assertEqual(element['name'], 'Shooter')
        finally:
            release.set()
            resolver.executor.shutdown(wait=True)

    def test_cached_type_is_available_while_request_runs(self):
        api = Mock(cache={('elements', 'doc', 'w', 'ws'): (0, [{'id': 'a', 'elementType': 'PARTSTUDIO', 'name': 'Old Name'}])}, disk_cache={})
        resolver = main.BackgroundResolver(api)
        resolver.executor.shutdown()
        resolver.executor = Mock()
        resolver.executor.submit.return_value = Future()
        _, _, element = resolver.resolve(('Robot', 'New Name', ('doc', 'w', 'ws', 'a')))
        self.assertEqual(element['elementType'], 'PARTSTUDIO')
        self.assertEqual(element['name'], 'New Name')

    def test_browser_accessibility_cannot_block_initial_title(self):
        future = Future()
        executor = Mock()
        executor.submit.return_value = future
        with patch.object(main, '_url_executor', executor), patch.object(main, '_url_pending', None), patch.object(main, '_tab_cache', None), patch.object(main, '_browser_state', {}):
            self.assertEqual(main.cached_tab(1, 'title', ('Robot', 'Intake')), ('Robot', 'Intake'))
            self.assertFalse(future.done())
            self.assertEqual(main._browser_state, {})
            future.set_result({'url': '', 'part_studio': True})
            self.assertEqual(main.cached_tab(2, 'different title', ('Robot', 'Shooter')), ('Robot', 'Shooter'))
            self.assertEqual(main._browser_state, {})

    def test_reopening_bypasses_spacing_but_edits_keep_limit(self):
        self.assertTrue(main.presence_due({'details': 'new'}, None, 101, 100))
        self.assertFalse(main.presence_due({'details': 'new'}, {'details': 'old'}, 101, 100))
        self.assertTrue(main.presence_due({'details': 'new'}, {'details': 'old'}, 105, 100))
        self.assertFalse(main.presence_due({'details': 'same'}, {'details': 'same'}, 110, 100))
