import unittest
from unittest.mock import Mock
import main


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

    def test_presence_keeps_images_private_and_links_to_onshape(self):
        document = {'id': 'doc', 'name': 'Robot', '_wvm': 'v'}
        element = {'id': 'studio', 'elementType': 'PARTSTUDIO'}
        payload = main.make_presence(document, element, 'Intake', 1, 'version')
        self.assertEqual(payload['large_image'], 'onshape_logo')
        self.assertEqual(payload['small_image'], 'onshape_logo')
        self.assertEqual(payload['buttons'], [{'label': 'View in Onshape',
                          'url': 'https://cad.onshape.com/documents/doc/v/version/e/studio'}])


if __name__ == '__main__':
    unittest.main()
