"""
Unit Tests for Machine Learning Models & Inference Pipeline
Mysuru Green Corridor Intelligent Traffic Management System (ITMS)
"""

import unittest
import time

from backend.ml_router import (
    api_predict_queue_flush,
    api_cv_vehicle_density,
    api_ml_corridor_overview,
    api_adaptive_preemption,
    PredictFlushRequest,
    AdaptivePreemptionRequest
)
from backend.ml.predictor import predict_queue_flush_time, fallback_flush_time, load_predictor
from backend.ml.cv_vehicle_counter import get_vehicle_counter, CorridorVehicleCounter

class TestMLPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Warm up ML model
        load_predictor()
        predict_queue_flush_time("J2_Irwin", vehicle_count=20, heavy_vehicle_ratio=0.10)

    def test_01_model_a_latency_under_50ms(self):
        """Verify that LightGBM queue flush inference executes strictly under 50ms (typically < 3ms)."""
        latencies = []
        for _ in range(30):
            t0 = time.perf_counter()
            res = predict_queue_flush_time(
                junction_id="J2_Irwin",
                vehicle_count=35,
                heavy_vehicle_ratio=0.18,
                hour=9,
                signal_phase="RED"
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            latencies.append(elapsed_ms)

        mean_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)

        print(f"\n[BENCHMARK] Model A Mean Latency: {mean_latency:.3f} ms, Max: {max_latency:.3f} ms")
        self.assertLess(mean_latency, 50.0, "Mean inference latency exceeds 50ms target")
        self.assertLess(max_latency, 50.0, "Peak inference latency exceeds 50ms threshold")
        self.assertTrue(res["is_ml_inferred"])
        self.assertGreater(res["predicted_flush_seconds"], 0.0)

    def test_02_model_a_predictions_across_junctions(self):
        """Verify queue flush outputs scale logically with traffic density and junction bottlenecks."""
        low = predict_queue_flush_time("J1_Ayurvedic", vehicle_count=10, heavy_vehicle_ratio=0.05)
        heavy = predict_queue_flush_time("J2_Irwin", vehicle_count=60, heavy_vehicle_ratio=0.30)

        self.assertGreater(heavy["predicted_flush_seconds"], low["predicted_flush_seconds"])
        self.assertGreater(heavy["recommended_preemption_lead_time_seconds"], heavy["predicted_flush_seconds"])

    def test_03_fallback_formula_integrity(self):
        """Verify fallback formula computes realistic clearance time if model is unavailable."""
        fallback = fallback_flush_time("J2_Irwin", vehicle_count=40, heavy_vehicle_ratio=0.20, signal_phase="RED")
        self.assertGreater(fallback, 20.0)
        self.assertLess(fallback, 300.0)

    def test_04_cv_node_feature_emission(self):
        """Verify Computer Vision detection node extracts vehicle counts and heavy vehicle ratios."""
        cv_counter = get_vehicle_counter()
        snapshot = cv_counter.generate_synthetic_junction_snapshot("J2_Irwin", sim_queue_estimate=25)

        self.assertIn("junction_id", snapshot)
        self.assertIn("vehicle_count", snapshot)
        self.assertIn("heavy_vehicle_ratio", snapshot)
        self.assertIn("breakdown", snapshot)

        self.assertEqual(snapshot["junction_id"], "J2_Irwin")
        self.assertGreater(snapshot["vehicle_count"], 0)
        self.assertGreaterEqual(snapshot["heavy_vehicle_ratio"], 0.0)
        self.assertLessEqual(snapshot["heavy_vehicle_ratio"], 1.0)

    def test_05_fastapi_predict_flush_handler(self):
        """Verify POST /api/ml/predict-flush handler returns valid JSON under 50ms."""
        req = PredictFlushRequest(
            junction_id="J2_Irwin",
            vehicle_count=30,
            heavy_vehicle_ratio=0.15,
            signal_phase="RED"
        )
        t0 = time.perf_counter()
        data = api_predict_queue_flush(req)
        endpoint_latency = (time.perf_counter() - t0) * 1000.0

        self.assertIn("predicted_flush_seconds", data)
        self.assertIn("recommended_preemption_lead_time_seconds", data)
        self.assertGreater(data["predicted_flush_seconds"], 0)
        self.assertLess(endpoint_latency, 50.0, f"Endpoint latency {endpoint_latency:.2f}ms exceeds 50ms limit")

    def test_06_adaptive_preemption_trigger(self):
        """Verify adaptive preemption triggers early green when queue flush exceeds available approach time."""
        # Scenario A: Queue requires high flush time, Ambulance ETA is low -> Early green REQUIRED
        req_early = AdaptivePreemptionRequest(
            vehicle_id="AMB-045-01",
            junction_id="J2_Irwin",
            eta_seconds=40.0,
            vehicle_count=60,
            heavy_vehicle_ratio=0.25
        )
        data_a = api_adaptive_preemption(req_early)
        self.assertTrue(data_a["early_preemption_triggered"])
        self.assertEqual(data_a["action"], "TRIGGER_EARLY_PREEMPTION")
        self.assertEqual(data_a["signal_command"], "FORCE_PHASE_GREEN")

        # Scenario B: Minor queue, high Ambulance ETA -> Standard cascade
        req_standard = AdaptivePreemptionRequest(
            vehicle_id="AMB-045-01",
            junction_id="J1_Ayurvedic",
            eta_seconds=120.0,
            vehicle_count=5,
            heavy_vehicle_ratio=0.0
        )
        data_b = api_adaptive_preemption(req_standard)
        self.assertFalse(data_b["early_preemption_triggered"])
        self.assertEqual(data_b["action"], "HOLD_STANDARD_WAVE")

    def test_07_corridor_status_multi_junction(self):
        """Verify GET /api/ml/corridor-status returns evaluations for all 3 junctions."""
        data = api_ml_corridor_overview()
        self.assertEqual(data["status"], "success")
        self.assertIn("J1_Ayurvedic", data["corridor_junctions"])
        self.assertIn("J2_Irwin", data["corridor_junctions"])
        self.assertIn("J3_KR_Hospital", data["corridor_junctions"])

if __name__ == "__main__":
    unittest.main()
