import unittest
from unittest.mock import Mock
import requests
import main
from snapshot_bridge import SnapshotBridge


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
        payload = main.make_presence(document, element, 'Intake', 1, 'onshape_logo')
        self.assertEqual(payload['details'], 'Tab: Intake')

    def test_tab_labels(self):
        for kind, label in [('PARTSTUDIO', 'Part Studio'), ('ASSEMBLY', 'Assembly'), ('DRAWING', 'Drawing')]:
            with self.subTest(kind=kind):
                payload = main.make_presence({'name': 'Robot'}, {'elementType': kind}, 'Intake', 1, 'image')
                self.assertEqual(payload['name'], 'Onshape')
                self.assertEqual(payload['details'], label + ': Intake')
        self.assertEqual(main.parse_title('Onshape - Robot | Intake - Brave'), ('Robot', 'Intake'))
        self.assertIsNone(main.parse_title('GitHub - Brave'))

    def test_thumbnail_server_exposes_only_registered_image(self):
        bridge = SnapshotBridge(port=0)
        try:
            base = 'http://127.0.0.1:' + str(bridge.server.server_port)
            image = b'\x89PNG\r\n\x1a\nexample'
            path = '/' + bridge.token + '/image.png'
            with bridge.lock:
                bridge.images[path] = image
            response = requests.get(base + path, timeout=3)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertEqual(response.content, image)
            for forbidden in ['/', '/.env', '/main.py', '/api/users/session', '/wrong/image.png']:
                self.assertEqual(requests.get(base + forbidden, timeout=3).status_code, 404)
            with bridge.lock:
                bridge.images.clear()
            self.assertEqual(requests.get(base + path, timeout=3).status_code, 404)
        finally:
            bridge.close()


if __name__ == '__main__':
    unittest.main()
