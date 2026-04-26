import unittest

import numpy as np

from daphnia_monitor import DaphniaMonitor


class DaphniaMonitorTests(unittest.TestCase):
    def test_low_motion_has_high_immobility(self):
        monitor = DaphniaMonitor()
        frame = np.zeros((80, 120), dtype=np.uint8)
        frames = [frame.copy() for _ in range(12)]

        metrics = monitor.analyze_frames(frames, fps=10)

        self.assertAlmostEqual(metrics.activity_score, 0.0, places=6)
        self.assertGreaterEqual(metrics.immobility_ratio, 0.95)

    def test_motion_increases_activity_and_speed(self):
        monitor = DaphniaMonitor()
        frames = []
        for step in range(12):
            frame = np.zeros((80, 120), dtype=np.uint8)
            x = 10 + step * 4
            y = 30
            frame[y : y + 3, x : x + 3] = 255
            frames.append(frame)

        metrics = monitor.analyze_frames(frames, fps=10)

        self.assertGreater(metrics.activity_score, 0.0)
        self.assertGreater(metrics.mean_speed_px_s, 0.0)
        self.assertLess(metrics.immobility_ratio, 1.0)

    def test_anomaly_flag_after_baseline_drop(self):
        monitor = DaphniaMonitor(baseline_windows=8)

        # Build active baseline first.
        for _ in range(8):
            active_frames = []
            for step in range(8):
                frame = np.zeros((80, 120), dtype=np.uint8)
                x = 20 + step * 5
                frame[40:43, x : x + 3] = 255
                active_frames.append(frame)
            monitor.analyze_frames(active_frames, fps=10)

        # Then simulate inactivity and expect an anomaly.
        still = np.zeros((80, 120), dtype=np.uint8)
        low_activity_metrics = monitor.analyze_frames([still.copy() for _ in range(8)], fps=10)

        self.assertEqual(low_activity_metrics.anomaly_flag, 1)
        self.assertGreater(low_activity_metrics.anomaly_score, 0.0)


if __name__ == "__main__":
    unittest.main()

