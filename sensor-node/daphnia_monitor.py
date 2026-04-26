import argparse
import time
from collections import deque
from dataclasses import dataclass
from statistics import median
from typing import Deque, List, Optional, Tuple

import numpy as np

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None


class CameraUnavailableError(RuntimeError):
    """Raised when camera access is requested but OpenCV is unavailable."""


@dataclass
class DaphniaMetrics:
    activity_score: float
    mean_speed_px_s: float
    immobility_ratio: float
    moving_centroid_dispersion_px: float
    anomaly_score: float
    anomaly_flag: int


class DaphniaMonitor:
    """Computes lightweight daphnia activity metrics from short frame windows."""

    def __init__(
        self,
        diff_threshold: int = 18,
        active_motion_fraction: float = 0.0005,
        baseline_windows: int = 24,
    ) -> None:
        self.diff_threshold = diff_threshold
        self.active_motion_fraction = active_motion_fraction
        self.activity_history: Deque[float] = deque(maxlen=baseline_windows)
        self.speed_history: Deque[float] = deque(maxlen=baseline_windows)
        self.immobility_history: Deque[float] = deque(maxlen=baseline_windows)

    @staticmethod
    def _to_grayscale(frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 2:
            return frame.astype(np.uint8)
        if frame.ndim == 3 and frame.shape[2] >= 3:
            # Use luma-ish weighted conversion for RGB/BGR frames.
            gray = (
                0.114 * frame[:, :, 0]
                + 0.587 * frame[:, :, 1]
                + 0.299 * frame[:, :, 2]
            )
            return gray.astype(np.uint8)
        raise ValueError("Unsupported frame shape for grayscale conversion")

    def analyze_frames(self, frames: List[np.ndarray], fps: float) -> DaphniaMetrics:
        if len(frames) < 2:
            raise ValueError("Need at least 2 frames to compute activity metrics")
        if fps <= 0:
            raise ValueError("fps must be > 0")

        gray_frames = [self._to_grayscale(frame) for frame in frames]

        activities: List[float] = []
        speeds: List[float] = []
        centroids: List[np.ndarray] = []

        previous_centroid: Optional[np.ndarray] = None
        for i in range(1, len(gray_frames)):
            prev = gray_frames[i - 1].astype(np.int16)
            cur = gray_frames[i].astype(np.int16)
            diff = np.abs(cur - prev)
            moving = diff > self.diff_threshold

            activity = float(np.count_nonzero(moving)) / float(moving.size)
            activities.append(activity)

            if np.any(moving):
                y_coords, x_coords = np.nonzero(moving)
                centroid = np.array([float(np.mean(x_coords)), float(np.mean(y_coords))])
                centroids.append(centroid)
                if previous_centroid is not None:
                    px_shift = float(np.linalg.norm(centroid - previous_centroid))
                    speeds.append(px_shift * fps)
                previous_centroid = centroid

        activity_score = float(np.mean(activities)) if activities else 0.0
        mean_speed = float(np.mean(speeds)) if speeds else 0.0
        active_fraction = (
            float(np.mean([a > self.active_motion_fraction for a in activities]))
            if activities
            else 0.0
        )
        immobility_ratio = 1.0 - active_fraction

        if len(centroids) >= 2:
            centroid_stack = np.vstack(centroids)
            dispersion = float(np.mean(np.std(centroid_stack, axis=0)))
        else:
            dispersion = 0.0

        anomaly_score, anomaly_flag = self._score_anomaly(
            activity_score, mean_speed, immobility_ratio
        )

        # Update baseline after scoring so the current window does not mask itself.
        self.activity_history.append(activity_score)
        self.speed_history.append(mean_speed)
        self.immobility_history.append(immobility_ratio)

        return DaphniaMetrics(
            activity_score=activity_score,
            mean_speed_px_s=mean_speed,
            immobility_ratio=immobility_ratio,
            moving_centroid_dispersion_px=dispersion,
            anomaly_score=anomaly_score,
            anomaly_flag=anomaly_flag,
        )

    @staticmethod
    def _robust_z(value: float, baseline: List[float]) -> float:
        if len(baseline) < 5:
            return 0.0
        baseline_median = median(baseline)
        abs_deviations = [abs(v - baseline_median) for v in baseline]
        mad = median(abs_deviations)
        if mad < 1e-9:
            if abs(value - baseline_median) < 1e-9:
                return 0.0
            return 8.0 if value > baseline_median else -8.0
        return (value - baseline_median) / (1.4826 * mad)

    def _score_anomaly(
        self, activity_score: float, mean_speed: float, immobility_ratio: float
    ) -> Tuple[float, int]:
        z_activity = self._robust_z(activity_score, list(self.activity_history))
        z_speed = self._robust_z(mean_speed, list(self.speed_history))
        z_immobility = self._robust_z(immobility_ratio, list(self.immobility_history))

        # Stress pattern: speed/activity dropping and immobility increasing.
        stress_score = max(0.0, -z_activity) + max(0.0, -z_speed) + max(0.0, z_immobility)
        anomaly_flag = int(stress_score >= 4.0)
        return float(stress_score), anomaly_flag

    @staticmethod
    def open_camera(camera_index: int = 0):
        if cv2 is None:
            raise CameraUnavailableError("OpenCV is not installed; camera capture unavailable")
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            raise CameraUnavailableError(f"Could not open camera index {camera_index}")
        return cap

    @staticmethod
    def capture_window(cap, duration_s: float = 10.0, fps_target: float = 10.0) -> List[np.ndarray]:
        if duration_s <= 0:
            raise ValueError("duration_s must be > 0")
        if fps_target <= 0:
            raise ValueError("fps_target must be > 0")

        frames: List[np.ndarray] = []
        next_frame_time = time.time()
        end_time = next_frame_time + duration_s
        frame_interval = 1.0 / fps_target

        while time.time() < end_time:
            now = time.time()
            if now < next_frame_time:
                time.sleep(max(0.0, next_frame_time - now))
                continue

            success, frame = cap.read()
            if success:
                frames.append(frame)
            next_frame_time += frame_interval

        return frames

    @staticmethod
    def to_payload(metrics: DaphniaMetrics) -> str:
        return (
            f"DAPH:A{metrics.activity_score:.3f},"
            f"S{metrics.mean_speed_px_s:.1f},"
            f"I{metrics.immobility_ratio:.2f},"
            f"D{metrics.moving_centroid_dispersion_px:.1f},"
            f"N{metrics.anomaly_flag}"
        )


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run daphnia activity monitor on a camera")
    parser.add_argument("--camera", type=int, default=0, help="Camera index for OpenCV")
    parser.add_argument("--window-seconds", type=float, default=10.0, help="Sample window length")
    parser.add_argument("--fps", type=float, default=10.0, help="Target capture FPS")
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable preview window (enabled by default)",
    )
    parser.add_argument(
        "--no-overlay",
        action="store_true",
        help="Disable metric overlay text in preview",
    )
    args = parser.parse_args()

    monitor = DaphniaMonitor()
    cap = DaphniaMonitor.open_camera(args.camera)

    if cv2 is not None:
        cap.set(cv2.CAP_PROP_FPS, args.fps)

    preview_enabled = not args.no_preview
    overlay_enabled = not args.no_overlay
    window_frame_count = max(2, int(args.window_seconds * args.fps))
    frame_interval_s = 1.0 / args.fps
    frames: List[np.ndarray] = []
    latest_metrics: Optional[DaphniaMetrics] = None
    latest_payload = "DAPH:NA"

    try:
        while True:
            loop_start = time.time()
            success, frame = cap.read()
            if not success:
                print("Camera frame read failed; retrying...")
                continue

            frames.append(frame)

            if len(frames) >= window_frame_count:
                metrics = monitor.analyze_frames(frames, fps=args.fps)
                latest_metrics = metrics
                latest_payload = DaphniaMonitor.to_payload(metrics)
                print(latest_payload)
                print(
                    "metrics: "
                    f"activity={metrics.activity_score:.4f}, "
                    f"speed_px_s={metrics.mean_speed_px_s:.2f}, "
                    f"immobility={metrics.immobility_ratio:.2f}, "
                    f"dispersion_px={metrics.moving_centroid_dispersion_px:.2f}, "
                    f"anomaly_score={metrics.anomaly_score:.2f}, "
                    f"anomaly_flag={metrics.anomaly_flag}"
                )
                frames.clear()

            if preview_enabled and cv2 is not None:
                preview_frame = frame.copy()
                if overlay_enabled:
                    cv2.putText(
                        preview_frame,
                        f"buffer: {len(frames)}/{window_frame_count}",
                        (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                        cv2.LINE_AA,
                    )
                    cv2.putText(
                        preview_frame,
                        latest_payload,
                        (10, 50),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )
                    if latest_metrics is not None:
                        cv2.putText(
                            preview_frame,
                            f"A:{latest_metrics.activity_score:.3f} S:{latest_metrics.mean_speed_px_s:.1f} "
                            f"I:{latest_metrics.immobility_ratio:.2f} N:{latest_metrics.anomaly_flag}",
                            (10, 72),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.5,
                            (255, 255, 0),
                            1,
                            cv2.LINE_AA,
                        )

                cv2.imshow("Daphnia Monitor", preview_frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    print("Stopping monitor (quit key).")
                    break

            elapsed = time.time() - loop_start
            sleep_time = max(0.0, frame_interval_s - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        cap.release()
        if cv2 is not None:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    _main()


