import unittest
from unittest.mock import Mock
from unittest.mock import patch
from io import BytesIO
import tempfile
import itertools
import threading
from pathlib import Path
import requests
from PIL import Image, ImageDraw
import main
from snapshot_bridge import SnapshotBridge, blur_snapshot, render_parameters, prepare_snapshot, should_blur


class PresenceTests(unittest.TestCase):
    def test_exact_element_id_resolves_duplicate_names(self):
        api = main.Onshape.__new__(main.Onshape)
        api.cache = {}
        api.get = Mock(side_effect=[{'id': 'doc', 'name': 'Robot'}, [
            {'id': 'assembly', 'name': 'Intake', 'elementType': 'ASSEMBLY'},
            {'id': 'studio', 'name': 'Intake', 'elementType': 'PARTSTUDIO'}]])
        document, context, element = api.resolve(('Robot', 'Intake', ('doc', 'v', 'version', 'studio')))
        self.assertEqual(element['elementType'], 'PARTSTUDIO')
        self.assertEqual(document['_wvm'], 'v')
        self.assertEqual(context, 'version')
        self.assertEqual(api.get.call_args.args[0], '/documents/d/doc/v/version/elements')

    def test_ambiguous_title_does_not_guess_type(self):
        api = main.Onshape.__new__(main.Onshape)
        api.cache = {}
        api.documents = Mock(return_value=[{'id': 'doc', 'name': 'Robot', 'defaultWorkspace': {'id': 'ws'}}])
        api.get = Mock(return_value=[{'id': 'a', 'name': 'Intake'}, {'id': 'b', 'name': 'Intake'}])
        document, _, element = api.resolve(('Robot', 'Intake'))
        self.assertIsNone(element)
        payload = main.make_presence(document, element, 'Intake', 1)
        self.assertEqual(payload['details'], 'Tab: Intake')

    def test_tab_labels(self):
        for kind, label in [('PARTSTUDIO', 'Part Studio'), ('ASSEMBLY', 'Assembly'), ('DRAWING', 'Drawing')]:
            with self.subTest(kind=kind):
                payload = main.make_presence({'name': 'Robot'}, {'elementType': kind}, 'Intake', 1)
                self.assertEqual(payload['name'], 'Onshape')
                self.assertEqual(payload['details'], label + ': Intake')
        self.assertEqual(main.parse_title('Onshape - Robot | Intake - Brave'), ('Robot', 'Intake'))
        self.assertIsNone(main.parse_title('GitHub - Brave'))

    def test_presence_links_to_onshape(self):
        document = {'id': 'doc', 'name': 'Robot', '_wvm': 'v'}
        element = {'id': 'studio', 'elementType': 'PARTSTUDIO'}
        payload = main.make_presence(document, element, 'Intake', 1, 'version')
        self.assertEqual(payload['large_image'], 'onshape_logo')
        self.assertEqual(payload['small_image'], 'onshape_logo')
        self.assertEqual(payload['buttons'], [{'label': 'View in Onshape',
                          'url': 'https://cad.onshape.com/documents/doc/v/version/e/studio'}])

    def test_server_publishes_blurred_bytes_only(self):
        image = Image.new('RGB', (300, 300), 'black')
        draw = ImageDraw.Draw(image)
        for x in range(50, 250, 4):
            draw.line((x, 50, x, 250), fill='white', width=1)
        original = BytesIO()
        image.save(original, 'PNG')
        raw = original.getvalue()
        api = Mock()
        api.get.side_effect = ValueError('Rendering unavailable')
        api.session.get.return_value.ok = True
        api.session.get.return_value.content = raw
        api.request.return_value = api.session.get.return_value
        bridge = SnapshotBridge(port=0)
        bridge.ensure_tunnel = Mock()
        base = 'http://127.0.0.1:' + str(bridge.server.server_port)
        bridge.hostname = base
        try:
            with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)):
                url = bridge.publish(api, {'id': 'doc'}, 'ws', {'id': 'tab', 'name': 'Intake', 'elementType': 'ASSEMBLY'})
                served = requests.get(url, timeout=3)
                self.assertEqual(served.content, blur_snapshot(raw))
                self.assertNotEqual(served.content, raw)
                blurred = Image.open(BytesIO(served.content))
                # Fine alternating stripes must lose nearly all contrast.
                self.assertLess(abs(blurred.getpixel((150, 150))[0] - blurred.getpixel((152, 150))[0]), 10)
                self.assertEqual(requests.get(base + '/.env', timeout=3).status_code, 404)
                bridge.clear()
                self.assertEqual(requests.get(url, timeout=3).status_code, 404)
        finally:
            bridge.close()

    def test_failed_blur_never_serves_original(self):
        api = Mock()
        api.session.get.return_value.ok = True
        api.session.get.return_value.content = b'\x89PNG\r\n\x1a\ninvalid image'
        api.request.return_value = api.session.get.return_value
        bridge = SnapshotBridge(port=0)
        bridge.ensure_tunnel = Mock()
        try:
            with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)):
                result = bridge.publish(api, {'id': 'doc'}, 'ws', {'id': 'tab', 'name': 'Intake', 'elementType': 'ASSEMBLY'})
            self.assertEqual(result, 'onshape_logo')
            self.assertEqual(bridge.images, {})
        finally:
            bridge.close()

    def test_snapshot_fits_both_ends_without_cutting_geometry(self):
        source = Image.new('RGB', (600, 200), 'red')
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 0, 100, 199), fill='lime')
        draw.rectangle((500, 0, 599, 199), fill='blue')
        data = BytesIO()
        source.save(data, 'PNG')
        result = Image.open(BytesIO(blur_snapshot(data.getvalue())))
        self.assertEqual(result.size, (300, 300))
        left, right = result.getpixel((35, 150)), result.getpixel((265, 150))
        self.assertGreater(left[1], left[0])
        self.assertGreater(right[2], right[0])
        self.assertEqual(result.getpixel((150, 30)), (43, 45, 49))

    def test_render_fits_all_corners_for_model_far_from_origin(self):
        bounds = {'lowX': 100, 'highX': 104, 'lowY': -80, 'highY': -70, 'lowZ': 20, 'highZ': 35}
        params = render_parameters(bounds)
        self.assertEqual(params['outputWidth'], 600)
        self.assertEqual(params['outputHeight'], 600)
        matrix = [float(v) for v in params['viewMatrix'].split(',')]
        for corner in itertools.product(*[(bounds['low'+a], bounds['high'+a]) for a in 'XYZ']):
            for offset in [0, 4]:
                projected = sum(matrix[offset+i] * corner[i] for i in range(3)) + matrix[offset+3]
                self.assertLessEqual(abs(projected) / params['pixelSize'], 284.00001)

    def test_biobuzz_is_always_blurred_and_other_documents_are_clear(self):
        with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)):
            self.assertTrue(should_blur({'id': 'protected', 'name': 'Biobuzz'}))
            self.assertTrue(should_blur({'id': 'protected', 'name': '  BIOBUZZ  '}))
            self.assertFalse(should_blur({'id': 'other', 'name': 'Pollen Bot'}))
            Path(directory, 'snapshot-settings.local.json').write_text(
                '{"blurred_document_ids": ["protected"]}')
            self.assertTrue(should_blur({'id': 'protected', 'name': 'Renamed Robot'}))
            Path(directory, 'snapshot-settings.json').write_text('invalid JSON')
            self.assertTrue(should_blur({'id': 'other', 'name': 'Pollen Bot'}))

    def test_document_rule_change_replaces_cached_clear_image(self):
        source = Image.new('RGB', (300, 300), 'black')
        ImageDraw.Draw(source).rectangle((140, 40, 160, 260), fill='white')
        raw = BytesIO()
        source.save(raw, 'PNG')
        bridge = SnapshotBridge(port=0)
        bridge.ensure_tunnel = Mock()
        bridge.hostname = 'http://127.0.0.1:' + str(bridge.server.server_port)
        api = Mock()
        document = {'id': 'doc', 'name': 'Other Robot'}
        element = {'id': 'tab', 'name': 'Intake', 'elementType': 'ASSEMBLY'}
        try:
            with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)), patch('snapshot_bridge.fetch_snapshot', return_value=raw.getvalue()):
                clear_url = bridge.publish(api, document, 'ws', element)
                self.assertEqual(requests.get(clear_url, timeout=3).content, prepare_snapshot(raw.getvalue(), False))
                Path(directory, 'snapshot-settings.local.json').write_text('{"blurred_document_ids": ["doc"]}')
                blurred_url = bridge.publish(api, document, 'ws', element)
                self.assertNotEqual(clear_url, blurred_url)
                self.assertEqual(requests.get(clear_url, timeout=3).status_code, 404)
                self.assertEqual(requests.get(blurred_url, timeout=3).content, blur_snapshot(raw.getvalue()))
        finally:
            bridge.close()

    def test_url_lookup_is_cached_but_refreshes_for_changed_title(self):
        main._tab_cache = None
        try:
            with patch('main.read_onshape_url', return_value='') as run, patch('main.time.monotonic', side_effect=[0, .5, .6, .9]):
                main.cached_tab(1, 'Onshape - Robot | Intake', ('Robot', 'Intake'))
                main.cached_tab(1, 'Onshape - Robot | Intake', ('Robot', 'Intake'))
                self.assertEqual(run.call_count, 1)
                main.cached_tab(1, 'Onshape - Robot | Shooter', ('Robot', 'Shooter'))
                self.assertEqual(run.call_count, 2)
                main.cached_tab(1, 'Onshape - Robot | Shooter', ('Robot', 'Shooter'))
                self.assertEqual(run.call_count, 2)
            with patch('main.read_onshape_url', return_value='') as run, patch('main.time.monotonic', return_value=2):
                main.cached_tab(1, 'Onshape - Robot | Shooter', ('Robot', 'Shooter'))
                self.assertEqual(run.call_count, 1)
        finally:
            main._tab_cache = None

    def test_background_render_does_not_block_or_serve_previous_tab(self):
        raw = BytesIO()
        Image.new('RGB', (600, 200), 'red').save(raw, 'PNG')
        release = threading.Event()
        def fetch(*args):
            release.wait(3)
            return raw.getvalue()
        bridge = SnapshotBridge(port=0)
        bridge.ensure_tunnel = Mock()
        bridge.hostname = 'http://127.0.0.1:' + str(bridge.server.server_port)
        api = Mock()
        doc = {'id': 'doc', 'name': 'Robot'}
        first = {'id': 'first', 'name': 'First', 'elementType': 'ASSEMBLY'}
        second = {'id': 'second', 'name': 'Second', 'elementType': 'ASSEMBLY'}
        try:
            with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)), patch('snapshot_bridge.fetch_snapshot', side_effect=fetch) as mocked:
                self.assertEqual(bridge.publish(api, doc, 'ws', first, blocking=False), 'onshape_logo')
                future = bridge.pending[1]
                self.assertFalse(future.done())
                self.assertEqual(bridge.publish(api, doc, 'ws', second, blocking=False), 'onshape_logo')
                release.set()
                future.result(timeout=3)
                # Completing First while viewing Second must never publish First.
                self.assertEqual(bridge.publish(api, doc, 'ws', second, blocking=False), 'onshape_logo')
                bridge.pending[1].result(timeout=3)
                url = bridge.publish(api, doc, 'ws', second, blocking=False)
                self.assertEqual(Image.open(BytesIO(requests.get(url, timeout=3).content)).size, (600, 600))
                self.assertEqual(mocked.call_count, 2)
                bridge.publish(api, doc, 'ws', second, blocking=False)
                self.assertEqual(mocked.call_count, 2)
        finally:
            release.set()
            bridge.close()

    def test_saved_preview_survives_restart_without_api_calls(self):
        source = Image.new('RGB', (300, 300), 'red')
        raw = BytesIO()
        source.save(raw, 'PNG')
        document = {'id': 'doc', 'name': 'Biobuzz'}
        element = {'id': 'tab', 'name': 'Intake', 'elementType': 'ASSEMBLY'}
        api = Mock()
        api.budget.available.return_value = True
        with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)), patch('snapshot_bridge.fetch_snapshot', return_value=raw.getvalue()) as fetch:
            first = SnapshotBridge(port=0)
            first.ensure_tunnel = Mock()
            first.hostname = 'http://127.0.0.1:' + str(first.server.server_port)
            try:
                first.publish(api, document, 'ws', element)
                self.assertEqual(fetch.call_count, 1)
            finally:
                first.close()
            second = SnapshotBridge(port=0)
            second.ensure_tunnel = Mock()
            second.hostname = 'http://127.0.0.1:' + str(second.server.server_port)
            api.budget.available.return_value = False
            try:
                url = second.publish(api, document, 'ws', element)
                self.assertEqual(requests.get(url, timeout=3).status_code, 200)
                self.assertEqual(fetch.call_count, 1)
            finally:
                second.close()


if __name__ == '__main__':
    unittest.main()
