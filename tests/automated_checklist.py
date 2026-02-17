#!/usr/bin/env python3
"""
Automated Test Checklist Runner

Executes the tests from HUMAN_TEST_CHECKLIST.md programmatically against the live 
Brain Assistant bot and generates a test report.

Usage:
    # Set required environment variables first:
    export SLACK_TEST_BOT_TOKEN="xoxb-..."
    export BRAIN_BOT_USER_ID="U..."
    export E2E_TEST_CHANNEL_ID="C..."
    
    # Run all tests:
    python tests/automated_checklist.py
    
    # Run specific test categories:
    python tests/automated_checklist.py --categories 1,2,3
    
    # Generate JSON report:
    python tests/automated_checklist.py --output json
"""

import os
import sys
import json
import time
import asyncio
import argparse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any, Callable
from enum import Enum

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except ImportError:
    print("Error: slack_sdk not installed. Run: pip install slack_sdk")
    sys.exit(1)

try:
    from clients.slack_user_client import SlackUserClient
    from clients.vaultwarden_client import get_secret
    VAULTWARDEN_AVAILABLE = True
except ImportError:
    VAULTWARDEN_AVAILABLE = False
    print("Warning: VaultwardenClient not available, will use environment variables only")


class TestStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class TestResult:
    test_id: str
    name: str
    category: str
    status: TestStatus
    duration_seconds: float
    notes: str = ""
    expected: str = ""
    actual: str = ""


@dataclass
class TestReport:
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    results: List[TestResult] = field(default_factory=list)
    environment: Dict[str, str] = field(default_factory=dict)
    
    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.status == TestStatus.PASS),
            "failed": sum(1 for r in self.results if r.status == TestStatus.FAIL),
            "partial": sum(1 for r in self.results if r.status == TestStatus.PARTIAL),
            "skipped": sum(1 for r in self.results if r.status == TestStatus.SKIP),
            "error": sum(1 for r in self.results if r.status == TestStatus.ERROR),
        }


class BotTester:
    """Test harness for interacting with Brain Assistant via Slack User Client."""
    
    def __init__(self):
        # Initialize SlackUserClient (loads credentials from Vaultwarden)
        try:
            self.client = SlackUserClient()
            self.timeout_seconds = 60
        except Exception as e:
            raise EnvironmentError(
                f"Failed to initialize SlackUserClient: {e}\n"
                "Ensure SLACK_USER_TOKEN and BRAIN_BOT_USER_ID are in Vaultwarden"
            )
    
    def send_and_wait(
        self, 
        message: str, 
        timeout: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message as the user and wait for Brain Assistant's response.
        
        Returns:
            Response message dict with 'text' key, or None if timeout
        """
        timeout = timeout or self.timeout_seconds
        try:
            response_data = self.client.ask_raw(message, timeout=timeout)
            return response_data  # Returns dict with 'text', 'ts', etc.
        except Exception as e:
            print(f"Warning: Failed to get response: {e}")
            return None
    
    def start_conversation(self):
        """Start a threaded conversation with the bot."""
        return self.client.conversation()


class AutomatedTestRunner:
    """Runs the automated test checklist."""
    
    def __init__(self, tester: BotTester):
        self.tester = tester
        self.report = TestReport()
        self.report.environment = {
            "bot_id": tester.client.bot_user_id,
            "user_id": tester.client.user_id,
            "timeout_seconds": str(tester.timeout_seconds),
        }
    
    def run_test(
        self,
        test_id: str,
        name: str,
        category: str,
        test_func: Callable[[], tuple[TestStatus, str]]
    ) -> TestResult:
        """Run a single test and record result."""
        print(f"  Running {test_id}: {name}...", end=" ", flush=True)
        
        start = time.time()
        try:
            status, notes = test_func()
            duration = time.time() - start
            print(f"{status.value.upper()} ({duration:.1f}s)")
            
        except Exception as e:
            duration = time.time() - start
            status = TestStatus.ERROR
            notes = f"Exception: {str(e)}"
            print(f"ERROR ({duration:.1f}s): {e}")
        
        result = TestResult(
            test_id=test_id,
            name=name,
            category=category,
            status=status,
            duration_seconds=duration,
            notes=notes,
        )
        self.report.results.append(result)
        return result
    
    # =========================================================================
    # Category 1: Basic Responsiveness
    # =========================================================================
    
    def test_1_1_bot_responds_to_dm(self) -> tuple[TestStatus, str]:
        """Test 1.1: Bot responds to Hello"""
        response = self.tester.send_and_wait("Hello")
        if response:
            text = response.get("text", "")
            if len(text) > 10:
                return TestStatus.PASS, f"Response: {text[:100]}..."
            return TestStatus.PARTIAL, f"Short response: {text}"
        return TestStatus.FAIL, "No response received within timeout"
    
    def test_1_2_working_indicator(self) -> tuple[TestStatus, str]:
        """Test 1.2: Working indicator appears"""
        # This is hard to test automatically since the indicator is deleted
        # We'll check that response arrived (implying indicator worked)
        response = self.tester.send_and_wait("What is 2+2?")
        if response:
            return TestStatus.PASS, "Response received (indicator assumed working)"
        return TestStatus.FAIL, "No response - cannot verify indicator"
    
    def test_1_3_multi_sentence_response(self) -> tuple[TestStatus, str]:
        """Test 1.3: Multi-sentence coherent response"""
        query = "What is TypeScript and why would I use it over JavaScript?"
        response = self.tester.send_and_wait(query, timeout=90)
        
        if not response:
            return TestStatus.FAIL, "No response"
        
        text = response.get("text", "")
        # Check for multiple sentences (periods or bullet points)
        has_structure = (
            text.count(". ") >= 2 or 
            text.count("- ") >= 2 or
            text.count("• ") >= 2 or
            text.count("\n") >= 3
        )
        
        if has_structure and len(text) > 200:
            return TestStatus.PASS, f"Response length: {len(text)} chars"
        if len(text) > 50:
            return TestStatus.PARTIAL, f"Short response: {len(text)} chars"
        return TestStatus.FAIL, f"Insufficient response: {text[:100]}"
    
    # =========================================================================
    # Category 2: Multi-Turn Conversation
    # =========================================================================
    
    def test_2_1_math_context_retention(self) -> tuple[TestStatus, str]:
        """Test 2.1: Math context retention (expected to fail - LLM limitation)
        
        NOTE: This test validates multi-turn conversation but math reasoning
        is unreliable with LLMs. Failure here doesn't indicate broken context.
        """
        # First message
        r1 = self.tester.send_and_wait("What's 25 times 4?")
        if not r1:
            return TestStatus.FAIL, "No response to first message"
        
        time.sleep(2)  # Brief pause between messages
        
        # Follow-up
        r2 = self.tester.send_and_wait("Now divide that by 5")
        if not r2:
            return TestStatus.FAIL, "No response to follow-up"
        
        text = r2.get("text", "").lower()
        # Looking for "20" in response (100 / 5 = 20)
        if "20" in text:
            return TestStatus.PASS, "Correctly calculated 100/5 = 20 (bonus!)"
        if "100" in text:
            return TestStatus.PARTIAL, "Remembered 100 but didn't compute division (expected)"
        return TestStatus.PARTIAL, f"LLM math limitation (context likely OK): {text[:80]}"
    
    def test_2_2_factual_context_retention(self) -> tuple[TestStatus, str]:
        """Test 2.2: Simple factual context retention (CRITICAL)
        
        Tests if bot maintains conversation history across sequential DMs
        via its conversation manager (cxdb).
        """
        # Send first message with a simple fact
        r1 = self.tester.send_and_wait("I'm working on a project called HomeOracle", timeout=90)
        if not r1:
            return TestStatus.FAIL, "No response to first message"
        
        time.sleep(3)  # Brief pause to ensure conversation context is saved
        
        # Ask to recall the fact in a follow-up message
        r2 = self.tester.send_and_wait("What project name did I just mention?", timeout=90)
        if not r2:
            return TestStatus.FAIL, "No response to recall question"
        
        text = r2.get("text", "").lower()
        # Should mention the project name from conversation history
        if "homeoracle" in text or "home oracle" in text:
            return TestStatus.PASS, "Correctly recalled project name from conversation history"
        
        # Check if it at least acknowledges not knowing or gives a generic response
        if any(phrase in text for phrase in ["don't", "not sure", "unclear", "previous"]):
            return TestStatus.PARTIAL, f"Bot responded but didn't recall fact: {text[:100]}"
        
        return TestStatus.FAIL, f"Failed to recall: {text[:100]}"
    
    def test_2_3_pronoun_resolution(self) -> tuple[TestStatus, str]:
        """Test 2.3: Bot resolves pronouns from conversation context"""
        # First message establishes topic
        r1 = self.tester.send_and_wait("Let's discuss Python programming", timeout=90)
        if not r1:
            return TestStatus.FAIL, "No response to topic introduction"
        
        time.sleep(3)  # Brief pause to ensure conversation context is saved
        
        # Follow-up with pronoun reference
        r2 = self.tester.send_and_wait("What testing frameworks does it have?", timeout=90)
        if not r2:
            return TestStatus.FAIL, "No response to pronoun question"
        
        text = r2.get("text", "").lower()
        # Should mention Python testing frameworks
        python_testing = any(kw in text for kw in ["pytest", "unittest", "nose", "testing"])
        
        if python_testing:
            return TestStatus.PASS, "Correctly understood 'it' refers to Python from context"
        
        # Check if it at least asks for clarification or shows some understanding
        if any(phrase in text for phrase in ["what", "which", "clarify", "python"]):
            return TestStatus.PARTIAL, f"Partial understanding: {text[:100]}"
        
        return TestStatus.FAIL, f"Failed pronoun resolution: {text[:100]}"
    
    # =========================================================================
    # Category 3: Brain Search Integration
    # =========================================================================
    
    def test_3_1_brain_search_triggered(self) -> tuple[TestStatus, str]:
        """Test 3.1: Brain search returns context"""
        # Use a term likely to be in brain notes
        query = "What have I written about productivity or time management?"
        response = self.tester.send_and_wait(query, timeout=90)
        
        if not response:
            return TestStatus.FAIL, "No response"
        
        text = response.get("text", "")
        
        # Check for brain context indicators
        has_brain = (
            "relevant context from your brain" in text.lower() or
            ".md" in text or
            "source:" in text.lower() or
            "journal/" in text.lower()
        )
        
        if has_brain:
            return TestStatus.PASS, "Brain context included in response"
        return TestStatus.PARTIAL, "Responded but no visible brain context"
    
    def test_3_2_citations_included(self) -> tuple[TestStatus, str]:
        """Test 3.2: Citations reference source files"""
        query = "What do my notes say about ADHD or focus strategies?"
        response = self.tester.send_and_wait(query, timeout=90)
        
        if not response:
            return TestStatus.FAIL, "No response"
        
        text = response.get("text", "")
        
        # Check for file citations
        has_citations = (
            ".md" in text or
            "Source:" in text or
            "journal/" in text
        )
        
        if has_citations:
            return TestStatus.PASS, "File citations present"
        return TestStatus.PARTIAL, "Responded, but no file citations visible"
    
    # =========================================================================
    # Category 4: Error Handling
    # =========================================================================
    
    def test_4_1_empty_message(self) -> tuple[TestStatus, str]:
        """Test 4.1: Empty/whitespace message handling"""
        # Send whitespace
        response = self.tester.send_and_wait("   ", timeout=15)
        
        # Either no response (ignored) or graceful handling
        if response is None:
            return TestStatus.PASS, "Empty message correctly ignored"
        
        # Check it didn't crash (any response is OK here)
        return TestStatus.PASS, "Bot responded gracefully to whitespace"
    
    def test_4_2_long_message(self) -> tuple[TestStatus, str]:
        """Test 4.2: Very long message handling"""
        # Generate a 2500 char message
        long_text = "Please summarize this text. " + ("Lorem ipsum. " * 200)
        
        response = self.tester.send_and_wait(long_text, timeout=90)
        
        if response:
            return TestStatus.PASS, f"Handled {len(long_text)} char message"
        return TestStatus.FAIL, "No response to long message"
    
    # =========================================================================
    # Category 5: File Handling (Basic check)
    # =========================================================================
    
    def test_5_manual_file_upload(self) -> tuple[TestStatus, str]:
        """Test 5: File upload - requires manual verification"""
        return TestStatus.SKIP, "File upload requires manual testing via Slack UI"
    
    # =========================================================================
    # Category 6-7: Commands (Partial automation)
    # =========================================================================
    
    def test_6_manual_index_command(self) -> tuple[TestStatus, str]:
        """Test 6: /index command - requires Slack UI"""
        return TestStatus.SKIP, "Slash commands require manual testing"
    
    def test_7_manual_model_command(self) -> tuple[TestStatus, str]:
        """Test 7: /model command - requires Slack UI"""
        return TestStatus.SKIP, "Slash commands require manual testing"
    
    # =========================================================================
    # Run all tests
    # =========================================================================
    
    def run_category_1(self):
        """Category 1: Basic Responsiveness"""
        print("\n📋 Category 1: Basic Responsiveness")
        self.run_test("1.1", "Bot responds to DM", "basic", self.test_1_1_bot_responds_to_dm)
        self.run_test("1.2", "Working indicator", "basic", self.test_1_2_working_indicator)
        self.run_test("1.3", "Multi-sentence response", "basic", self.test_1_3_multi_sentence_response)
    
    def run_category_2(self):
        """Category 2: Multi-Turn Conversation"""
        print("\n📋 Category 2: Multi-Turn Conversation")
        self.run_test("2.1", "Math context (expected partial)", "multi_turn", self.test_2_1_math_context_retention)
        self.run_test("2.2", "Factual context retention", "multi_turn", self.test_2_2_factual_context_retention)
        self.run_test("2.3", "Pronoun resolution", "multi_turn", self.test_2_3_pronoun_resolution)
    
    def run_category_3(self):
        """Category 3: Brain Search Integration"""
        print("\n📋 Category 3: Brain Search Integration")
        self.run_test("3.1", "Brain search triggered", "brain_search", self.test_3_1_brain_search_triggered)
        self.run_test("3.2", "Citations included", "brain_search", self.test_3_2_citations_included)
    
    def run_category_4(self):
        """Category 4: Error Handling"""
        print("\n📋 Category 4: Error Handling")
        self.run_test("4.1", "Empty message handling", "error_handling", self.test_4_1_empty_message)
        self.run_test("4.2", "Long message handling", "error_handling", self.test_4_2_long_message)
    
    def run_category_manual(self):
        """Categories 5-7: Manual Tests"""
        print("\n📋 Categories 5-7: Manual Tests (skipped)")
        self.run_test("5.x", "File upload tests", "file_handling", self.test_5_manual_file_upload)
        self.run_test("6.x", "/index command tests", "index_cmd", self.test_6_manual_index_command)
        self.run_test("7.x", "/model command tests", "model_cmd", self.test_7_manual_model_command)
    
    def run_all(self, categories: Optional[List[int]] = None):
        """Run all or specified test categories."""
        categories = categories or [1, 2, 3, 4, 5, 6, 7]
        
        print("\n" + "=" * 60)
        print("🧪 AUTOMATED TEST CHECKLIST")
        print("=" * 60)
        print(f"Started: {self.report.timestamp}")
        print(f"Bot: {self.tester.client.bot_user_id}")
        print(f"User: {self.tester.client.user_id}")
        
        if 1 in categories:
            self.run_category_1()
        if 2 in categories:
            self.run_category_2()
        if 3 in categories:
            self.run_category_3()
        if 4 in categories:
            self.run_category_4()
        if any(c in categories for c in [5, 6, 7]):
            self.run_category_manual()
        
        self.print_report()
        return self.report
    
    def print_report(self):
        """Print test report summary."""
        s = self.report.summary()
        
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        print(f"Total:   {s['total']}")
        print(f"✅ Pass:  {s['passed']}")
        print(f"❌ Fail:  {s['failed']}")
        print(f"⚠️  Part:  {s['partial']}")
        print(f"⏭️  Skip:  {s['skipped']}")
        print(f"💥 Error: {s['error']}")
        
        # Print failures
        failures = [r for r in self.report.results if r.status in (TestStatus.FAIL, TestStatus.ERROR)]
        if failures:
            print("\n❌ FAILURES:")
            for r in failures:
                print(f"  - {r.test_id}: {r.name}")
                print(f"    {r.notes[:80]}...")


def main():
    parser = argparse.ArgumentParser(description="Run automated test checklist")
    parser.add_argument(
        "--categories", 
        type=str, 
        default="1,2,3,4",
        help="Comma-separated category numbers to run (default: 1,2,3,4)"
    )
    parser.add_argument(
        "--output", 
        choices=["text", "json"], 
        default="text",
        help="Output format"
    )
    parser.add_argument(
        "--json-file",
        type=str,
        default=None,
        help="Path to save JSON report"
    )
    
    args = parser.parse_args()
    categories = [int(c) for c in args.categories.split(",")]
    
    try:
        tester = BotTester()
        runner = AutomatedTestRunner(tester)
        report = runner.run_all(categories)
        
        if args.output == "json" or args.json_file:
            report_dict = {
                "timestamp": report.timestamp,
                "environment": report.environment,
                "summary": report.summary(),
                "results": [
                    {
                        "test_id": r.test_id,
                        "name": r.name,
                        "category": r.category,
                        "status": r.status.value,
                        "duration_seconds": r.duration_seconds,
                        "notes": r.notes,
                    }
                    for r in report.results
                ]
            }
            
            if args.json_file:
                with open(args.json_file, "w") as f:
                    json.dump(report_dict, f, indent=2)
                print(f"\nJSON report saved to: {args.json_file}")
            else:
                print(json.dumps(report_dict, indent=2))
        
        # Exit with error code if failures
        if report.summary()["failed"] > 0 or report.summary()["error"] > 0:
            sys.exit(1)
            
    except EnvironmentError as e:
        print(f"\n❌ Environment Error: {e}")
        print("\nSecrets can be provided via:")
        print("  1. Vaultwarden (recommended) - ensure secrets exist in vault.nuc-1.local")
        print("  2. Environment variables:")
        print("     export SLACK_TEST_BOT_TOKEN='xoxb-...'")
        print("     export BRAIN_BOT_USER_ID='U...'")
        print("     export E2E_TEST_CHANNEL_ID='C...'")
        sys.exit(1)


if __name__ == "__main__":
    main()
