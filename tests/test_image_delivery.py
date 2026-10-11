import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch
from image_delivery import ImageDelivery
from snapshot_bridge import SnapshotBridge


class ImageDeliveryTests(unittest.TestCase):
    def delivery(self):
        delivery = ImageDelivery()
        delivery.executor.shutdown()
        delivery.executor = Mock()
        future = Future()
        delivery.executor.submit.return_value = future
        return delivery, future

    def test_broken_image_falls_back_and_reports_failure(self):
        delivery, future = self.delivery()
        failure = Mock()
        url = 'https://example.com/model.png'
        self.assertEqual(delivery.image(url, 'fallback', failure), 'fallback')
        future.set_result(False)
        self.assertEqual(delivery.image(url, 'fallback', failure), 'fallback')
        failure.assert_called_once_with(url)
        self.assertEqual(delivery.executor.submit.call_count, 1)

    def test_verified_image_appears_then_failed_recheck_removes_it(self):
        delivery, future = self.delivery()
        url = 'https://example.com/model.png'
        with patch('image_delivery.time.monotonic', return_value=0):
            delivery.image(url, 'fallback')
            future.set_result(True)
            self.assertEqual(delivery.image(url, 'fallback'), url)
        recheck = Future()
        delivery.executor.submit.return_value = recheck
        with patch('image_delivery.time.monotonic', return_value=61):
            self.assertEqual(delivery.image(url, 'fallback'), url)
            recheck.set_result(False)
            self.assertEqual(delivery.image(url, 'fallback'), 'fallback')

    def test_http_error_and_non_png_are_rejected(self):
        response = Mock(status_code=404)
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        with patch('image_delivery.requests.get', return_value=response):
            self.assertFalse(ImageDelivery.reachable('https://example.com/image'))
            response.status_code = 200
            response.iter_content.return_value = iter([b'<html>'])
            self.assertFalse(ImageDelivery.reachable('https://example.com/image'))
            response.iter_content.return_value = iter([b'\x89PNG\r\n\x1a\n'])
            self.assertTrue(ImageDelivery.reachable('https://example.com/image'))

    def test_only_current_failed_tunnel_is_restarted(self):
        bridge = SnapshotBridge.__new__(SnapshotBridge)
        bridge.hostname = 'https://current.trycloudflare.com'
        bridge.process = Mock()
        bridge.process.poll.return_value = None
        process = bridge.process
        bridge.image_failed('https://old.trycloudflare.com/image.png')
        process.terminate.assert_not_called()
        bridge.image_failed('https://current.trycloudflare.com/image.png')
        process.terminate.assert_called_once()
        self.assertIsNone(bridge.hostname)
        self.assertIsNone(bridge.process)
