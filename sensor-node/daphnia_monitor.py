import argparse
import time
from collections import deque
from dataclasses import dataclass
from statistics import median
from typing import Deque, Dict, List, Optional, Tuple

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
            if cv2 is not None:
                return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Fallback if OpenCV is unavailable.
            gray = 0.114 * frame[:, :, 0] + 0.587 * frame[:, :, 1] + 0.299 * frame[:, :, 2]
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
            f"Z{metrics.anomaly_score:.2f},"
            f"N{metrics.anomaly_flag}"
        )


def _processed_view_and_centroids(
    previous_gray: Optional[np.ndarray],
    frame: np.ndarray,
    diff_threshold: int,
    processing_scale: float = 0.6,
    blur_kernel: int = 3,
    open_kernel_mat: Optional[np.ndarray] = None,
    dilate_kernel_mat: Optional[np.ndarray] = None,
    dilate_iterations: int = 1,
    min_area_px: int = 8,
) -> Tuple[np.ndarray, List[Tuple[float, float]], np.ndarray]:
    gray = DaphniaMonitor._to_grayscale(frame)
    centroids: List[Tuple[float, float]] = []

    if previous_gray is None or cv2 is None:
        return gray, centroids, gray

    scale = min(1.0, max(0.2, processing_scale))
    if scale < 0.999:
        gray_proc = cv2.resize(gray, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        prev_proc = cv2.resize(
            previous_gray,
            (gray_proc.shape[1], gray_proc.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    else:
        gray_proc = gray
        prev_proc = previous_gray

    if blur_kernel > 1:
        if blur_kernel % 2 == 0:
            blur_kernel += 1
        gray_for_diff = cv2.GaussianBlur(gray_proc, (blur_kernel, blur_kernel), 0)
        previous_for_diff = cv2.GaussianBlur(prev_proc, (blur_kernel, blur_kernel), 0)
    else:
        gray_for_diff = gray_proc
        previous_for_diff = prev_proc

    diff = cv2.absdiff(gray_for_diff, previous_for_diff)
    _, motion_mask = cv2.threshold(diff, diff_threshold, 255, cv2.THRESH_BINARY)
    if open_kernel_mat is not None:
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, open_kernel_mat)
    if dilate_iterations > 0 and dilate_kernel_mat is not None:
        motion_mask = cv2.dilate(motion_mask, dilate_kernel_mat, iterations=dilate_iterations)

    count, labels, stats, component_centroids = cv2.connectedComponentsWithStats(
        motion_mask,
        connectivity=8,
    )
    valid_labels: List[int] = []
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area_px:
            continue
        c_x = float(component_centroids[label][0])
        c_y = float(component_centroids[label][1])
        if scale < 0.999:
            c_x /= scale
            c_y /= scale
        centroids.append((c_x, c_y))
        valid_labels.append(label)

    if valid_labels:
        valid_mask = np.isin(labels, np.array(valid_labels, dtype=labels.dtype))
        motion_mask = np.where(valid_mask, 255, 0).astype(np.uint8)
    else:
        motion_mask.fill(0)

    if scale < 0.999:
        motion_mask = cv2.resize(
            motion_mask,
            (gray.shape[1], gray.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

    return motion_mask, centroids, gray


def _update_track_ids(
    detected_centroids: List[Tuple[float, float]],
    tracks: Dict[int, Tuple[float, float]],
    track_age: Dict[int, int],
    frame_index: int,
    next_track_id: int,
    max_match_distance_px: float = 30.0,
    max_stale_frames: int = 20,
) -> Tuple[List[Tuple[int, Tuple[float, float]]], int]:
    labeled_points: List[Tuple[int, Tuple[float, float]]] = []
    available_ids = set(tracks.keys())

    for cx, cy in detected_centroids:
        best_id: Optional[int] = None
        best_distance = max_match_distance_px
        for track_id in list(available_ids):
            tx, ty = tracks[track_id]
            distance = float(np.hypot(cx - tx, cy - ty))
            if distance < best_distance:
                best_distance = distance
                best_id = track_id

        if best_id is None:
            best_id = next_track_id
            next_track_id += 1
        else:
            available_ids.remove(best_id)

        tracks[best_id] = (cx, cy)
        track_age[best_id] = frame_index
        labeled_points.append((best_id, (cx, cy)))

    stale_ids = [
        track_id
        for track_id, last_seen in track_age.items()
        if frame_index - last_seen > max_stale_frames
    ]
    for track_id in stale_ids:
        tracks.pop(track_id, None)
        track_age.pop(track_id, None)

    return labeled_points, next_track_id


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run daphnia activity monitor on a camera")
    parser.add_argument("--camera", type=int, default=0, help="Camera index for OpenCV")
    parser.add_argument("--window-seconds", type=float, default=10.0, help="Sample window length")
    parser.add_argument("--fps", type=float, default=10.0, help="Target capture FPS")
    parser.add_argument(
        "--diff-threshold",
        type=int,
        default=10,
        help="Pixel-difference threshold for motion detection (lower is more sensitive)",
    )
    parser.add_argument(
        "--min-area-px",
        type=int,
        default=3,
        help="Minimum connected-component area to keep as a daphnia candidate",
    )
    parser.add_argument(
        "--blur-kernel",
        type=int,
        default=3,
        help="Gaussian blur kernel size before differencing (odd numbers are best)",
    )
    parser.add_argument(
        "--open-kernel",
        type=int,
        default=2,
        help="Morphological open kernel size (0 disables)",
    )
    parser.add_argument(
        "--dilate-iterations",
        type=int,
        default=1,
        help="How much to dilate motion mask so tiny moving blobs are retained",
    )
    parser.add_argument(
        "--processed-scale",
        type=float,
        default=0.6,
        help="Scale factor for processed-view computation (0.2-1.0; lower is faster)",
    )
    parser.add_argument(
        "--processed-every-n",
        type=int,
        default=1,
        help="Update processed visualization every N frames (higher is faster)",
    )
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

    monitor = DaphniaMonitor(diff_threshold=args.diff_threshold)
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
    previous_gray: Optional[np.ndarray] = None
    tracks: Dict[int, Tuple[float, float]] = {}
    track_age: Dict[int, int] = {}
    next_track_id = 1
    frame_index = 0
    last_processed_gray: Optional[np.ndarray] = None
    last_labeled_points: List[Tuple[int, Tuple[float, float]]] = []
    open_kernel_mat: Optional[np.ndarray] = None
    if args.open_kernel > 0:
        open_kernel_mat = np.ones((args.open_kernel, args.open_kernel), np.uint8)
    dilate_kernel_mat: Optional[np.ndarray] = None
    if args.dilate_iterations > 0:
        dilate_kernel_mat = np.ones((2, 2), np.uint8)
    processed_every_n = max(1, args.processed_every_n)

    try:
        while True:
            loop_start = time.time()
            success, frame = cap.read()
            if not success:
                print("Camera frame read failed; retrying...")
                continue

            frame_index += 1

            frames.append(frame)

            if preview_enabled and cv2 is not None:
                should_update_processed = (frame_index % processed_every_n) == 0
                if should_update_processed:
                    processed_gray, centroids, current_gray = _processed_view_and_centroids(
                        previous_gray,
                        frame,
                        diff_threshold=monitor.diff_threshold,
                        processing_scale=args.processed_scale,
                        blur_kernel=max(0, args.blur_kernel),
                        open_kernel_mat=open_kernel_mat,
                        dilate_kernel_mat=dilate_kernel_mat,
                        dilate_iterations=max(0, args.dilate_iterations),
                        min_area_px=max(1, args.min_area_px),
                    )
                    last_labeled_points, next_track_id = _update_track_ids(
                        centroids,
                        tracks,
                        track_age,
                        frame_index,
                        next_track_id,
                    )
                    previous_gray = current_gray
                    last_processed_gray = processed_gray
                else:
                    current_gray = DaphniaMonitor._to_grayscale(frame)
                    previous_gray = current_gray

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

                if last_processed_gray is None:
                    last_processed_gray = DaphniaMonitor._to_grayscale(frame)
                processed_frame = last_processed_gray.copy()
                for track_id, (cx, cy) in last_labeled_points:
                    x = int(cx)
                    y = int(cy)
                    cv2.circle(processed_frame, (x, y), 5, 255, 1)
                    cv2.putText(
                        processed_frame,
                        f"ID:{track_id}",
                        (x + 6, max(12, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        255,
                        1,
                        cv2.LINE_AA,
                    )
                cv2.putText(
                    processed_frame,
                    f"detections: {len(last_labeled_points)}",
                    (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    255,
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("Daphnia Processed", processed_frame)

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


