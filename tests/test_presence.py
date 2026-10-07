import unittest
from unittest.mock import Mock
from unittest.mock import patch
from io import BytesIO
import tempfile
from pathlib import Path
import requests
from PIL import Image, ImageDraw
import main
from snapshot_bridge import SnapshotBridge, blur_snapshot


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
        api.session.get.return_value.ok = True
        api.session.get.return_value.content = raw
        bridge = SnapshotBridge(port=0)
        bridge.ensure_tunnel = Mock()
        base = 'http://127.0.0.1:' + str(bridge.server.server_port)
        bridge.hostname = base
        try:
            with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)):
                url = bridge.publish(api, {'id': 'doc'}, 'ws', {'id': 'tab', 'name': 'Intake', 'elementType': 'PARTSTUDIO'})
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
        bridge = SnapshotBridge(port=0)
        bridge.ensure_tunnel = Mock()
        try:
            with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)):
                result = bridge.publish(api, {'id': 'doc'}, 'ws', {'id': 'tab'})
            self.assertEqual(result, 'onshape_logo')
            self.assertEqual(bridge.images, {})
        finally:
            bridge.close()


if __name__ == '__main__':
    unittest.main()
