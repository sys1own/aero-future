import os
import tempfile
import unittest

import blueprint_parser
import orchestrator
from builder_brains import parameter_tuner


class TestScalingHotfixes(unittest.TestCase):
    def test_dynamic_anomaly_ceiling_scales_with_target_count(self):
        self.assertEqual(blueprint_parser.get_anomaly_ceiling([]), 50)
        self.assertEqual(blueprint_parser.get_anomaly_ceiling(["f"] * 5000), 250)
        self.assertEqual(blueprint_parser.get_anomaly_ceiling(["f"] * 20000), 1000)

    def test_toml_parse_attaches_parser_validation(self):
        minimal = """
[system]
name = "scale-test"
strategy = "DIRECT_COMPILE"

[context_registry.core_logic]
path = "./app.py"
language = "python"
"""
        with tempfile.NamedTemporaryFile("w", suffix=".aero", delete=False, encoding="utf-8") as handle:
            handle.write(minimal)
            blueprint_path = handle.name

        try:
            context = blueprint_parser.parse_blueprint(blueprint_path)
        finally:
            os.remove(blueprint_path)

        parser_validation = context.get("parser_validation", {})
        self.assertEqual(parser_validation.get("scan_targets"), ["./app.py"])
        self.assertEqual(parser_validation.get("anomaly_ceiling"), 50)
        self.assertEqual(parser_validation.get("parameter_validation_failures"), 0)

    def test_write_gate_requires_real_output(self):
        self.assertTrue(orchestrator.should_write_aeroc("DIRECT_COMPILE", 1, 128))
        self.assertFalse(orchestrator.should_write_aeroc("DIRECT_COMPILE", 0, 128))
        self.assertFalse(orchestrator.should_write_aeroc("DIRECT_COMPILE", 1, 0))

    def test_blueprint_strategy_is_preserved_under_high_anomaly_pressure(self):
        metadata = {
            "blueprint_strategy": "DIRECT_COMPILE",
            "resolved_strategy": "AGGRESSIVE_MUTATION",
            "strategy_mode": "aggressive_decomposition",
            "selected_action_label": "execute_polyglot_decomposition",
            "anomaly_count": 50,
            "anomaly_ceiling": 50,
        }
        orchestrator._honor_blueprint_strategy(metadata)
        self.assertEqual(metadata["resolved_strategy"], "DIRECT_COMPILE")
        self.assertEqual(metadata["strategy_mode"], "direct_compile")
        self.assertEqual(metadata["selected_action_label"], "honor_blueprint_strategy")

    def test_parameter_tuner_forwards_current_config_without_reset(self):
        current_config = {"learning_rate": 0.1254321, "mutation_sigma": 0.05}
        forwarded = parameter_tuner._forward_current_config(current_config)
        self.assertEqual(
            forwarded,
            {"learning_rate": 0.125432, "mutation_sigma": 0.05},
        )


if __name__ == "__main__":
    unittest.main()
