import contextlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import nebula_deploy as deploy


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {"ssh": {"host": "example.test", "user": "deploy"},
                       "source_dir": str(self.root), "remote_dir": "/opt/test"}

    def run_local(self, commands, health="", **settings):
        plan = {"remote_dir": "/opt/test", "commands": commands, "healthcheck": health}
        config = {**self.config, "execution": {"healthcheck_interval": 0, **settings}}
        def local(_config, command, **kwargs):
            return subprocess.run(command, shell=True, capture_output=True, text=True, timeout=20)
        with patch.object(deploy, "run_remote", side_effect=local):
            return deploy.run_plan(config, plan, False)

    def test_old_config_gets_defaults(self):
        path = self.root / "config.json"
        path.write_text(json.dumps(self.config))
        self.assertEqual(deploy.load_config(str(path))["execution"], deploy.EXECUTION_DEFAULTS)

    def test_invalid_execution_settings(self):
        path = self.root / "config.json"
        for value in (True, 0, -1, "5", 61):
            path.write_text(json.dumps({**self.config, "execution": {"healthcheck_attempts": value}}))
            with self.assertRaises(ValueError):
                deploy.load_config(str(path))

    def test_health_eventually_ready_without_rerunning_commands(self):
        marker = shlex.quote(str(self.root / "marker"))
        counter = shlex.quote(str(self.root / "counter"))
        health = f'n=$(cat {counter} 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > {counter}; test "$n" -ge 3'
        result = self.run_local([f"echo run >> {marker}"], health)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / "marker").read_text(), "run\n")
        self.assertEqual((self.root / "counter").read_text(), "3\n")

    def test_failed_health_stops_after_limit(self):
        result = self.run_local(["true"], "exit 7", healthcheck_attempts=2)
        self.assertEqual(result.returncode, 7)
        self.assertIn("failed after 2 attempts", result.stderr)

    def test_command_timeout_stops_following_commands(self):
        result = self.run_local(["sleep 3", "echo SHOULD_NOT_RUN"], command_timeout=1)
        self.assertEqual(result.returncode, 124)
        self.assertNotIn("SHOULD_NOT_RUN", result.stdout)

    def test_health_timeout(self):
        result = self.run_local(["true"], "sleep 3", healthcheck_timeout=1, healthcheck_attempts=1)
        self.assertEqual(result.returncode, 124)

    def execute_mock(self, upload_error=None, repair_error=None):
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            with patch.object(deploy, "upload_source", side_effect=upload_error, return_value="abc"), \
                 patch.object(deploy, "run_plan", return_value=subprocess.CompletedProcess([], 1 if repair_error else 0, "output", "")), \
                 patch.object(deploy, "repair_plan", side_effect=repair_error), \
                 contextlib.redirect_stdout(io.StringIO()):
                plan = {"remote_dir": "/opt/test", "commands": ["true"]}
                if upload_error or repair_error:
                    with self.assertRaises(RuntimeError):
                        deploy.execute(self.config, plan, False, 1)
                else:
                    self.assertEqual(deploy.execute(self.config, plan, False, 0), 0)
            log = next((self.root / "runs").glob("*.json"))
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)
            return json.loads(log.read_text())
        finally:
            os.chdir(previous)

    def test_upload_failure_is_logged(self):
        record = self.execute_mock(upload_error=RuntimeError("upload failed"))
        self.assertEqual(record["failed_stage"], "uploading")
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["attempts"], [])

    def test_repair_failure_preserves_attempt(self):
        record = self.execute_mock(repair_error=RuntimeError("AI unavailable"))
        self.assertEqual(record["failed_stage"], "repairing")
        self.assertEqual(record["attempts"][0]["returncode"], 1)

    def test_success_is_logged(self):
        record = self.execute_mock()
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(record["source_sha256"], "abc")


if __name__ == "__main__":
    unittest.main()
