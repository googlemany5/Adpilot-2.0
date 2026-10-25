import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
SAFETY = ROOT / "safety.py"


class BackendReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text()
        cls.tree = ast.parse(cls.source)
        cls.routes = {}
        for node in ast.walk(cls.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                func = decorator.func
                if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "app"
                ):
                    path = None
                    if decorator.args and isinstance(
                        decorator.args[0], ast.Constant
                    ):
                        path = decorator.args[0].value
                    if isinstance(path, str):
                        cls.routes.setdefault(path, []).append(node.name)

    def test_core_routes_exist(self):
        expected = [
            "/health",
            "/auth/register",
            "/auth/login",
            "/auth/me",
            "/campaigns",
            "/campaigns/{campaign_id}/budget",
            "/campaigns/{campaign_id}/experiments",
            "/campaigns/{campaign_id}/optimization",
            "/campaigns/{campaign_id}/safety",
            "/campaigns/{campaign_id}/safe-spend",
            "/campaigns/{campaign_id}/validate-allocations",
            "/campaigns/{campaign_id}/pause",
            "/campaigns/{campaign_id}/resume",
            "/campaigns/{campaign_id}/emergency-pause",
            "/platforms/status",
            "/campaigns/{campaign_id}/platform-execution-preview",
            "/campaigns/{campaign_id}/platform-execute",
            "/campaigns/{campaign_id}/run-ai",
            "/ai/market-discovery",
            "/ai/regional-discovery",
            "/ai/experiment-plan",
            "/ai/learn",
            "/ai/growth-plan",
            "/campaigns/{campaign_id}/growth-plan",
            "/campaigns/{campaign_id}/generate-and-save-growth-plan",
            "/campaigns/{campaign_id}/dashboard",
            "/campaigns/{campaign_id}/analytics",
            "/campaigns/{campaign_id}/budget-status",
            "/system/backend-capabilities",
        ]
        missing = [path for path in expected if path not in self.routes]
        self.assertEqual([], missing, f"Missing expected routes: {missing}")

    def test_growth_plan_payload_is_wired_once(self):
        matches = [
            node for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "adpilot_generate_and_save_growth_plan"
        ]
        self.assertEqual(1, len(matches), "Expected exactly one growth-plan save function")
        fn = matches[0]
        args = [arg.arg for arg in fn.args.args]
        self.assertEqual(
            1, args.count("payload"),
            "Growth-plan function must have exactly one payload parameter",
        )

        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "endpoint"
        ]
        self.assertTrue(calls, "Growth-plan endpoint call not found")
        payload_calls = [
            call for call in calls
            if sum(kw.arg == "payload" for kw in call.keywords) == 1
        ]
        self.assertTrue(
            payload_calls,
            "Growth-plan endpoint call must pass payload exactly once",
        )

    def test_safe_spend_uses_safety_alias(self):
        fn = next(
            (
                node for node in ast.walk(self.tree)
                if isinstance(node, ast.FunctionDef)
                and node.name == "safe_spend"
            ),
            None,
        )
        self.assertIsNotNone(fn, "safe_spend endpoint not found")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "safety_record_spend"
        ]
        self.assertTrue(
            calls,
            "safe_spend should call the imported safety_record_spend alias",
        )

    def test_platform_execution_route_and_guard_test_exist(self):
        route = "/campaigns/{campaign_id}/platform-execute"
        self.assertIn(route, self.routes, "Platform execution route is missing")
        guard_test = ROOT / "test_platform_execution_guard.py"
        self.assertTrue(
            guard_test.exists(),
            "Dedicated platform execution guard test is missing",
        )

    def test_safety_module_exists(self):
        self.assertTrue(SAFETY.exists(), "safety.py is missing")
        safety_tree = ast.parse(SAFETY.read_text())
        names = {
            node.name for node in safety_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("record_spend", names)
        self.assertTrue(
            any("safe" in name.lower() or "budget" in name.lower()
                for name in names),
            "Review safety.py: no clearly named safety/budget helper found",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
