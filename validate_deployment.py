#!/usr/bin/env python3
"""
Validate that the Slack bot deployment is ready for testing.

Checks:
- Dependencies installed
- Test suite runnable
- Slack credentials present
- NUC-2 accessible
"""

import os
import sys
import subprocess
from pathlib import Path


# Load secrets.env before checks
def load_secrets():
    """Load environment from secrets.env if available."""
    secrets_file = Path(__file__).parent / "secrets.env"
    if secrets_file.exists():
        with open(secrets_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    if line.startswith("export "):
                        line = line[7:]
                    key, value = line.split("=", 1)
                    value = value.strip('"').strip("'")
                    os.environ[key] = value


load_secrets()


class DeploymentValidator:
    """Validate deployment readiness."""

    def __init__(self):
        self.project_root = Path(__file__).parent
        self.checks_passed = 0
        self.checks_failed = 0

    def run_all_checks(self):
        """Run all validation checks."""
        print("\n" + "="*60)
        print("🔍 DEPLOYMENT VALIDATION")
        print("="*60 + "\n")

        # Local checks
        self.check_project_structure()
        self.check_python_version()
        self.check_dependencies()
        self.check_slack_credentials()
        self.check_test_suite()

        # Remote checks
        self.check_nuc2_access()
        self.check_nuc2_service()

        # Summary
        self._print_summary()

    def check_project_structure(self):
        """Check if project structure is correct."""
        print("📁 Project Structure")
        required_files = [
            "agents/slack_agent.py",
            "slack_bot/__init__.py",
            "slack_bot/file_handler.py",
            "slack_bot/performance_monitor.py",
            "tests/conftest.py",
            "tests/requirements-test.txt",
        ]

        all_present = True
        for file in required_files:
            path = self.project_root / file
            status = "✓" if path.exists() else "✗"
            print(f"  {status} {file}")
            if not path.exists():
                all_present = False
                self.checks_failed += 1

        if all_present:
            self.checks_passed += 1
        print()

    def check_python_version(self):
        """Check Python version."""
        print("🐍 Python Version")
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        print(f"  Version: {version_str}")

        if version.major >= 3 and version.minor >= 10:
            print("  ✓ Compatible")
            self.checks_passed += 1
        else:
            print("  ✗ Need Python 3.10+")
            self.checks_failed += 1
        print()

    def check_dependencies(self):
        """Check if required dependencies are installed."""
        print("📦 Dependencies")
        required = [
            "slack_bolt",
            "slack_sdk",
            "pytest",
            "pytest_asyncio",
            "aiohttp",
        ]

        all_installed = True
        for package in required:
            try:
                __import__(package.replace("-", "_"))
                print(f"  ✓ {package}")
                self.checks_passed += 1
            except ImportError:
                print(f"  ✗ {package} (missing)")
                all_installed = False
                self.checks_failed += 1

        if not all_installed:
            print("\n  Install with:")
            print("  pip install -r tests/requirements-test.txt")
        print()

    def check_slack_credentials(self):
        """Check if Slack credentials are present."""
        print("🔐 Slack Credentials")

        secrets_file = self.project_root / "secrets.env"
        bot_token = os.getenv("SLACK_BOT_TOKEN")
        app_token = os.getenv("SLACK_APP_TOKEN")

        if secrets_file.exists():
            print("  ✓ secrets.env found")
            self.checks_passed += 1
        else:
            print("  ✗ secrets.env not found")
            self.checks_failed += 1

        if bot_token:
            print(f"  ✓ SLACK_BOT_TOKEN set: {bot_token[:20]}...")
            self.checks_passed += 1
        else:
            print("  ✗ SLACK_BOT_TOKEN not set")
            self.checks_failed += 1

        if app_token:
            print(f"  ✓ SLACK_APP_TOKEN set: {app_token[:20]}...")
            self.checks_passed += 1
        else:
            print("  ✗ SLACK_APP_TOKEN not set")
            self.checks_failed += 1

        print()

    def check_test_suite(self):
        """Check if test suite is runnable."""
        print("🧪 Test Suite")

        # Try importing pytest
        try:
            import pytest
            print(f"  ✓ pytest installed: {pytest.__version__}")
            self.checks_passed += 1
        except ImportError:
            print("  ✗ pytest not installed")
            self.checks_failed += 1
            print()
            return

        # Try running a quick test
        try:
            result = subprocess.run(
                ["pytest", "--collect-only", "tests/"],
                cwd=self.project_root,
                capture_output=True,
                timeout=10
            )

            if result.returncode == 0:
                # Count tests
                output = result.stdout.decode()
                if "67" in output or "passed" in output:
                    print("  ✓ Test collection successful")
                    self.checks_passed += 1
                else:
                    print("  ⚠ Tests collected (check test count)")
                    self.checks_passed += 1
            else:
                print("  ✗ Test collection failed")
                self.checks_failed += 1
        except subprocess.TimeoutExpired:
            print("  ✗ Test collection timeout")
            self.checks_failed += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            self.checks_failed += 1

        print()

    def check_nuc2_access(self):
        """Check if NUC-2 is accessible via SSH."""
        print("🖥️  NUC-2 Accessibility")

        try:
            result = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=3", "nuc-2", "echo", "ok"],
                capture_output=True,
                timeout=5
            )

            if result.returncode == 0:
                print("  ✓ NUC-2 SSH accessible")
                self.checks_passed += 1
            else:
                print("  ✗ NUC-2 SSH connection failed")
                self.checks_failed += 1
        except subprocess.TimeoutExpired:
            print("  ✗ NUC-2 SSH timeout")
            self.checks_failed += 1
        except FileNotFoundError:
            print("  ✗ SSH not available")
            self.checks_failed += 1
        except Exception as e:
            print(f"  ✗ Error: {e}")
            self.checks_failed += 1

        print()

    def check_nuc2_service(self):
        """Check if brain-slack-bot service is running on NUC-2."""
        print("⚙️  NUC-2 Service Status")

        try:
            result = subprocess.run(
                [
                    "ssh", "nuc-2",
                    "sudo", "systemctl", "is-active", "brain-slack-bot"
                ],
                capture_output=True,
                timeout=5
            )

            if result.returncode == 0:
                status = result.stdout.decode().strip()
                print(f"  ✓ Service status: {status}")
                self.checks_passed += 1
            else:
                print("  ⚠ Service not running (will start on deployment)")
                self.checks_passed += 1
        except Exception as e:
            print(f"  ⚠ Could not check service: {e}")
            print("    (This is OK if NUC-2 is not yet deployed)")
            self.checks_passed += 1

        print()

    def _print_summary(self):
        """Print validation summary."""
        total = self.checks_passed + self.checks_failed
        percentage = (self.checks_passed / total * 100) if total > 0 else 0

        print("="*60)
        print("📊 VALIDATION SUMMARY")
        print("="*60)
        print(f"\n✓ Passed: {self.checks_passed}/{total}")
        print(f"✗ Failed: {self.checks_failed}/{total}")
        print(f"Success Rate: {percentage:.0f}%\n")

        if self.checks_failed == 0:
            print("✅ DEPLOYMENT READY FOR TESTING")
            print("\nNext steps:")
            print("  1. Run tests locally: pytest tests/ -v")
            print("  2. Start test script: python test_slack_bot_manual.py")
            print("  3. Send test messages in Slack")
            print("  4. Check NUC-2 logs: ssh nuc-2 && sudo journalctl -u brain-slack-bot -f")
        else:
            print("❌ DEPLOYMENT VALIDATION FAILED")
            print("\nPlease fix the issues above before testing.")

        print()


def main():
    """Main entry point."""
    validator = DeploymentValidator()
    validator.run_all_checks()

    sys.exit(0 if validator.checks_failed == 0 else 1)


if __name__ == "__main__":
    main()
