import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import requests
from active_url import UrlReader
from feature_activity import feature_activity
from snapshot_bridge import SnapshotBridge
from main import make_presence
from feature_badge import SOURCES, feature_badge, static_badge_url
from PIL import Image
from io import BytesIO


class FeatureTests(unittest.TestCase):
    def test_all_bundled_native_icons_render_and_idle_is_branded(self):
        for name in SOURCES:
            with self.subTest(name=name):
                self.assertEqual(Image.open(BytesIO(feature_badge(name))).size, (1024, 1024))
        self.assertNotEqual(feature_badge('Idle'), feature_badge('Extrude'))

    def test_renamed_features_use_editor_help_link(self):
        for topic, label in [('extrude', 'Extrude'), ('sketch_tools', 'Sketch'), ('linear_pattern', 'Linear Pattern')]:
            activity = feature_activity({'available': True, 'part_studio': True, 'feature': {
                'name': 'Custom Name', 'help_url': 'https://cad.onshape.com/help/index.htm#cshid='+topic}})
            self.assertEqual(activity, {'label': label, 'name': 'Custom Name'})

    def test_idle_does_not_guess_from_toolbar_or_saved_features(self):
        observation = {'available': True, 'part_studio': True, 'feature': None,
                       'toolbar': ['Sketch', 'Extrude'], 'features': ['Extrude 72']}
        self.assertEqual(feature_activity(observation)['label'], 'Idle')
        self.assertEqual(feature_activity({})['label'], 'Unavailable')
        self.assertEqual(feature_activity({'available': True, 'part_studio': False})['label'], 'Unavailable')

    def test_name_fallback_and_unknown_custom_feature(self):
        observation = {'available': True, 'part_studio': True, 'feature': {'name': 'Extrude 72'}}
        self.assertEqual(feature_activity(observation)['label'], 'Extrude')
        observation['feature'] = {'name': 'My Custom Tool', 'help_url': 'https://example.com/#cshid=extrude'}
        self.assertEqual(feature_activity(observation), {'label': 'Feature', 'name': 'My Custom Tool'})

    def test_part_studio_feature_text_and_assembly_text(self):
        doc = {'id': 'doc', 'name': 'Biobuzz'}
        element = {'id': 'tab', 'elementType': 'PARTSTUDIO'}
        payload = make_presence(doc, element, 'Turret', 1, 'ws', {'label': 'Sketch', 'name': 'Sketch 67'})
        self.assertEqual(payload['details'], 'Part Studio: Turret · Sketch 67')
        self.assertEqual(payload['state'], 'Document: Biobuzz')
        renamed = make_presence(doc, element, 'Turret', 1, activity={'label': 'Extrude', 'name': 'Motor Mount'})
        self.assertEqual(renamed['details'], 'Part Studio: Turret · Extrude: Motor Mount')
        self.assertEqual(make_presence(doc, element, 'Turret', 1, activity={'label': 'Idle', 'name': ''})['state'],
                         'Document: Biobuzz')
        element['elementType'] = 'ASSEMBLY'
        self.assertEqual(make_presence(doc, element, 'Turret', 1, activity={'label': 'Idle', 'name': ''})['state'],
                         'Document: Biobuzz')

    def test_feature_badge_replaces_snapshot_without_api_requests(self):
        bridge = SnapshotBridge(port=0)
        bridge.ensure_tunnel = Mock()
        bridge.hostname = 'http://127.0.0.1:' + str(bridge.server.server_port)
        old_path = '/old-model.png'
        bridge.images[old_path] = b'old image'
        api = Mock()
        element = {'id': 'tab', 'name': 'Turret', 'elementType': 'PARTSTUDIO'}
        try:
            with tempfile.TemporaryDirectory() as directory, patch('snapshot_bridge.ROOT', Path(directory)), patch('snapshot_bridge.fetch_snapshot') as fetch:
                self.assertEqual(bridge.publish(api, {'id': 'doc'}, 'ws', element), 'onshape_logo')
                url = bridge.publish_feature({'id': 'doc', 'name': 'Biobuzz'}, element, {'label': 'Extrude', 'name': 'Extrude 72'})
                self.assertEqual(url, static_badge_url('Extrude'))
                symbol = bridge.publish_symbol('Assembly')
                self.assertEqual(symbol, static_badge_url('Assembly', compact=True))
                bridge.hostname = None
                self.assertEqual(bridge.publish_feature({'id': 'doc', 'name': 'Biobuzz'}, element,
                                 {'label': 'Viewing', 'name': ''}), static_badge_url('Viewing'))
                bridge.ensure_tunnel.assert_not_called()
                self.assertEqual(requests.get('http://127.0.0.1:' + str(bridge.server.server_port) + old_path, timeout=3).status_code, 404)
                status = json.loads(Path(directory, 'snapshot-status.json').read_text())
                self.assertFalse(status['model_snapshot'])
                self.assertEqual(status['feature']['label'], 'Viewing')
                fetch.assert_not_called()
                api.request.assert_not_called()
                api.get.assert_not_called()
        finally:
            bridge.close()

    def test_bad_helper_reply_is_unavailable(self):
        reader = UrlReader()
        for reply in ['', 'not JSON', '[]']:
            with patch.object(reader, 'read', return_value=reply):
                self.assertEqual(reader.read_state('Onshape'), {})

