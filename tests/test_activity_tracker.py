import unittest
from activity_tracker import ActivityTracker, SessionTimer
from main import make_presence

class ActivityTrackerTests(unittest.TestCase):
    def test_session_time_survives_switches_and_short_loading_gaps(self):
        timer = SessionTimer()
        self.assertIsNone(timer.update(False, 0))
        self.assertEqual(timer.update(True, 100), 100)
        self.assertEqual(timer.update(True, 200), 100)
        timer.update(False, 210)
        self.assertEqual(timer.update(True, 220), 100)
        timer.update(False, 230)
        self.assertIsNone(timer.update(False, 260))
        self.assertEqual(timer.update(True, 300), 300)

    def test_closed_feature_is_retained_until_fifteen_minutes(self):
        tracker = ActivityTracker()
        feature = {'label': 'Extrude', 'name': 'Extrude 72'}
        sample = {'foreground': True, 'tick': 1, 'age': 0}
        self.assertEqual(tracker.update('studio', 'PARTSTUDIO', feature, sample, 0), feature)
        closed = {'label': 'Idle', 'name': ''}
        self.assertEqual(tracker.update('studio', 'PARTSTUDIO', closed, sample, 899), feature)
        self.assertEqual(tracker.update('studio', 'PARTSTUDIO', closed, sample, 900)['label'], 'Idle')

    def test_open_editor_can_go_idle_and_resumes_with_input(self):
        tracker = ActivityTracker()
        feature = {'label': 'Sketch', 'name': 'Sketch 1'}
        sample = {'foreground': True, 'tick': 1, 'age': 0}
        tracker.update('studio', 'PARTSTUDIO', feature, sample, 0)
        self.assertEqual(tracker.update('studio', 'PARTSTUDIO', feature, sample, 901)['label'], 'Idle')
        sample['tick'] = 2
        self.assertEqual(tracker.update('studio', 'PARTSTUDIO', feature, sample, 902), feature)

    def test_other_apps_do_not_reset_assembly_timer(self):
        tracker = ActivityTracker()
        observed = {'label': 'Unavailable', 'name': ''}
        tracker.update('assembly', 'ASSEMBLY', observed, {'foreground': True, 'tick': 1, 'age': 0}, 0)
        self.assertEqual(tracker.update('assembly', 'ASSEMBLY', observed, {'foreground': False, 'tick': 2, 'age': 0}, 901)['label'], 'Idle')
        self.assertEqual(tracker.update('assembly', 'ASSEMBLY', observed, {'foreground': True, 'tick': 3, 'age': 0}, 902)['label'], 'Assembly')

    def test_features_stay_with_their_own_tab_and_viewing_has_grace(self):
        tracker = ActivityTracker()
        sample = {'foreground': True, 'tick': 1, 'age': 0}
        feature = {'label': 'Sketch', 'name': 'Sketch 1'}
        tracker.update('one', 'PARTSTUDIO', feature, sample, 0)
        closed = {'label': 'Idle', 'name': ''}
        self.assertEqual(tracker.update('two', 'PARTSTUDIO', closed, sample, 10)['label'], 'Viewing')
        self.assertEqual(tracker.update('one', 'PARTSTUDIO', closed, sample, 20), feature)

    def test_idle_assembly_keeps_document_on_its_own_line(self):
        payload = make_presence({'name': 'Biobuzz'}, {'elementType': 'ASSEMBLY'}, 'Full Robot', 1,
                                activity={'label': 'Idle', 'name': ''})
        self.assertEqual(payload['details'], 'Assembly: Full Robot · Idle')
        self.assertEqual(payload['state'], 'Document: Biobuzz')
