#!/usr/bin/env python3
"""
Brain Tuner — Dynamic conversational testing agent for Brain Assistant.

Conducts multi-turn conversations with the live bot to evaluate and tune:
- Conversation memory (does it remember what you told it?)
- Context balance (does it over-rely on brain search vs. chat history?)
- Personality (is it warm, concise, and on-point?)

Usage:
    # Quick 5-turn name recall test
    python tools/brain_tuner.py --scenario name-recall

    # Full conversation evaluation suite
    python tools/brain_tuner.py --scenario all

    # Custom scenario
    python tools/brain_tuner.py --scenario custom --turns 8

    # Verbose output with bot logs
    python tools/brain_tuner.py --scenario name-recall --verbose
"""

import os
import re
import sys
import json
import time
import argparse
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.slack_user_client import SlackUserClient, BotResponseTimeout


# ============================================================================
# Evaluation framework
# ============================================================================

class Verdict(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass
class TurnResult:
    """Result of a single conversation turn."""
    turn_number: int
    user_message: str
    bot_response: str
    duration_seconds: float
    checks: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def passed_all(self) -> bool:
        return all(c["verdict"] == Verdict.PASS for c in self.checks)


@dataclass
class ScenarioResult:
    """Result of a complete conversation scenario."""
    scenario_name: str
    turns: List[TurnResult] = field(default_factory=list)
    verdict: Verdict = Verdict.PASS
    summary: str = ""
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0

    @property
    def total_checks(self) -> int:
        return sum(len(t.checks) for t in self.turns)

    @property
    def passed_checks(self) -> int:
        return sum(
            1 for t in self.turns
            for c in t.checks
            if c["verdict"] == Verdict.PASS
        )


# ============================================================================
# Conversation engine
# ============================================================================

class ConversationEngine:
    """Drives multi-turn conversations with the bot and evaluates responses."""

    def __init__(self, verbose: bool = False, timeout: int = 90):
        self.client = SlackUserClient(timeout=timeout)
        self.verbose = verbose
        self.timeout = timeout

    def chat(self, message: str) -> Tuple[str, float]:
        """Send a message and get the bot's response with timing.

        Returns:
            Tuple of (response_text, duration_seconds)
        """
        start = time.time()
        try:
            response = self.client.ask(message, timeout=self.timeout)
            duration = time.time() - start
            if self.verbose:
                print(f"  [Bot ({duration:.1f}s)]: {response[:200]}")
            return response, duration
        except BotResponseTimeout:
            duration = time.time() - start
            if self.verbose:
                print(f"  [Bot TIMEOUT after {duration:.1f}s]")
            return "", duration

    def evaluate(self, response: str, checks: List[Dict]) -> List[Dict[str, Any]]:
        """Evaluate a bot response against a list of checks.

        Each check is a dict with:
            name: Human-readable name
            type: "contains", "not_contains", "min_length", "regex", "callable"
            value: The check value (string, int, or callable)
            weight: Optional weight for scoring (default 1)

        Returns:
            List of check results with verdict.
        """
        results = []
        resp_lower = response.lower()

        for check in checks:
            name = check["name"]
            check_type = check["type"]
            value = check["value"]
            result = {"name": name, "type": check_type, "verdict": Verdict.FAIL, "detail": ""}

            if check_type == "contains":
                terms = value if isinstance(value, list) else [value]
                found = [t for t in terms if t.lower() in resp_lower]
                if found:
                    result["verdict"] = Verdict.PASS
                    result["detail"] = f"Found: {found}"
                else:
                    result["detail"] = f"Missing all of: {terms}"

            elif check_type == "contains_any":
                terms = value if isinstance(value, list) else [value]
                found = [t for t in terms if t.lower() in resp_lower]
                if found:
                    result["verdict"] = Verdict.PASS
                    result["detail"] = f"Found: {found}"
                else:
                    result["detail"] = f"None found from: {terms}"

            elif check_type == "not_contains":
                terms = value if isinstance(value, list) else [value]
                found = [t for t in terms if t.lower() in resp_lower]
                if not found:
                    result["verdict"] = Verdict.PASS
                    result["detail"] = "Correctly absent"
                else:
                    result["detail"] = f"Unwanted terms found: {found}"

            elif check_type == "min_length":
                if len(response) >= value:
                    result["verdict"] = Verdict.PASS
                    result["detail"] = f"Length {len(response)} >= {value}"
                else:
                    result["detail"] = f"Length {len(response)} < {value}"

            elif check_type == "regex":
                if re.search(value, response, re.IGNORECASE):
                    result["verdict"] = Verdict.PASS
                    result["detail"] = f"Matched: {value}"
                else:
                    result["detail"] = f"No match for: {value}"

            elif check_type == "callable":
                try:
                    passed, detail = value(response)
                    result["verdict"] = Verdict.PASS if passed else Verdict.FAIL
                    result["detail"] = detail
                except Exception as e:
                    result["verdict"] = Verdict.ERROR
                    result["detail"] = str(e)

            results.append(result)

        return results


# ============================================================================
# Scenarios
# ============================================================================

def scenario_name_recall(engine: ConversationEngine) -> ScenarioResult:
    """5-turn name recall: bot remembers who we are and what name we gave it.

    Turn 1: Introduce ourselves and give the bot a name
    Turn 2: Chat about something else
    Turn 3: Ask about something unrelated
    Turn 4: Return to the name topic indirectly
    Turn 5: Directly ask for recall
    """
    result = ScenarioResult(scenario_name="name-recall")
    start = time.time()

    # Unique identifiers for this run
    run_id = datetime.now().strftime("%H%M%S")
    bot_name = "Archie"
    user_project = "Project Nova"  # Use natural spacing so bot can recall either form

    turns = [
        {
            "message": f"Hey! I'd like to call you {bot_name} from now on. My current project is called {user_project}.",
            "checks": [
                {"name": "Acknowledges bot name", "type": "contains_any", "value": [bot_name.lower(), "name", "call me"]},
                {"name": "Reasonable response", "type": "min_length", "value": 20},
            ],
        },
        {
            "message": "What do you know about graph databases? Just a quick overview.",
            "checks": [
                {"name": "Answers about graph DBs", "type": "contains_any", "value": ["graph", "node", "edge", "neo4j", "relationship"]},
                {"name": "Doesn't hallucinate recall", "type": "not_contains", "value": ["don't remember", "no context"]},
            ],
        },
        {
            "message": "How would you compare REST vs GraphQL for a new API project?",
            "checks": [
                {"name": "Discusses REST/GraphQL", "type": "contains_any", "value": ["rest", "graphql", "api", "query", "endpoint"]},
                {"name": "Substantive answer", "type": "min_length", "value": 100},
            ],
        },
        {
            "message": "Going back to our earlier chat — what was the name I gave you?",
            "checks": [
                {"name": f"Recalls bot name '{bot_name}'", "type": "contains", "value": [bot_name.lower()]},
            ],
        },
        {
            "message": "And what project am I working on right now?",
            "checks": [
                {"name": f"Recalls project '{user_project}'", "type": "contains", "value": [user_project.lower()]},
            ],
        },
    ]

    for i, turn_spec in enumerate(turns):
        turn_num = i + 1
        print(f"  Turn {turn_num}/5: {turn_spec['message'][:60]}...")

        response, duration = engine.chat(turn_spec["message"])
        checks = engine.evaluate(response, turn_spec["checks"])

        turn = TurnResult(
            turn_number=turn_num,
            user_message=turn_spec["message"],
            bot_response=response,
            duration_seconds=duration,
            checks=checks,
        )
        result.turns.append(turn)

        # Print check results
        for check in checks:
            icon = "✅" if check["verdict"] == Verdict.PASS else "❌"
            print(f"    {icon} {check['name']}: {check['detail'][:80]}")

        # Brief pause between turns
        if i < len(turns) - 1:
            time.sleep(2)

    # Determine overall verdict
    t4_passed = result.turns[3].passed_all if len(result.turns) > 3 else False
    t5_passed = result.turns[4].passed_all if len(result.turns) > 4 else False

    if t4_passed and t5_passed:
        result.verdict = Verdict.PASS
        result.summary = f"Bot recalled '{bot_name}' and '{user_project}' after 5 turns"
    elif t4_passed or t5_passed:
        result.verdict = Verdict.PARTIAL
        result.summary = f"Partial recall: name={t4_passed}, project={t5_passed}"
    else:
        result.verdict = Verdict.FAIL
        result.summary = f"Bot failed to recall both '{bot_name}' and '{user_project}'"

    result.duration_seconds = time.time() - start
    return result


def scenario_context_vs_search(engine: ConversationEngine) -> ScenarioResult:
    """Tests whether the bot prioritizes conversation over brain search.

    Tells the bot a specific fact, then asks a question that brain search
    might answer differently. The bot should prioritize what we just told it.
    """
    result = ScenarioResult(scenario_name="context-vs-search")
    start = time.time()

    turns = [
        {
            "message": (
                "I've decided to switch my main programming language from Python to Rust "
                "for my next project. This is a big decision for me."
            ),
            "checks": [
                {"name": "Acknowledges decision", "type": "contains_any", "value": ["rust", "switch", "decision", "change"]},
            ],
        },
        {
            "message": "What language am I planning to use for my next project?",
            "checks": [
                {"name": "Says Rust (from conversation)", "type": "contains", "value": ["rust"]},
                {"name": "Doesn't say Python (brain might)", "type": "not_contains", "value": ["python is your main"]},
            ],
        },
        {
            "message": "Why did I say I'm making this change?",
            "checks": [
                {"name": "Recalls it was a big decision", "type": "contains_any", "value": ["big decision", "important", "significant", "decided", "switch"]},
            ],
        },
    ]

    for i, turn_spec in enumerate(turns):
        turn_num = i + 1
        print(f"  Turn {turn_num}/3: {turn_spec['message'][:60]}...")

        response, duration = engine.chat(turn_spec["message"])
        checks = engine.evaluate(response, turn_spec["checks"])

        turn = TurnResult(
            turn_number=turn_num,
            user_message=turn_spec["message"],
            bot_response=response,
            duration_seconds=duration,
            checks=checks,
        )
        result.turns.append(turn)

        for check in checks:
            icon = "✅" if check["verdict"] == Verdict.PASS else "❌"
            print(f"    {icon} {check['name']}: {check['detail'][:80]}")

        if i < len(turns) - 1:
            time.sleep(2)

    all_passed = all(t.passed_all for t in result.turns)
    result.verdict = Verdict.PASS if all_passed else Verdict.FAIL
    result.summary = "Bot correctly prioritizes conversation context over brain search" if all_passed else "Bot failed to prioritize conversation context"
    result.duration_seconds = time.time() - start
    return result


def scenario_personality_continuity(engine: ConversationEngine) -> ScenarioResult:
    """Tests personality consistency and natural conversation flow."""
    result = ScenarioResult(scenario_name="personality-continuity")
    start = time.time()

    turns = [
        {
            "message": "I'm feeling a bit overwhelmed with all my projects today.",
            "checks": [
                {"name": "Empathetic response", "type": "contains_any",
                 "value": ["understand", "overwhelming", "lot", "help", "manage", "break", "prioriti", "feel"]},
                {"name": "Not dismissive", "type": "not_contains", "value": ["just do", "simple", "easy"]},
            ],
        },
        {
            "message": "Yeah, I have three projects going: a Rust CLI, a Slack bot, and a data pipeline.",
            "checks": [
                {"name": "Acknowledges all three", "type": "callable", "value": lambda r: (
                    sum(1 for kw in ["rust", "cli", "slack", "bot", "data", "pipeline"] if kw in r.lower()) >= 3,
                    f"Mentioned {sum(1 for kw in ['rust', 'cli', 'slack', 'bot', 'data', 'pipeline'] if kw in r.lower())}/6 keywords"
                )},
            ],
        },
        {
            "message": "Which one do you think I should focus on first?",
            "checks": [
                {"name": "References specific projects", "type": "contains_any",
                 "value": ["rust", "slack", "data", "pipeline", "cli"]},
                {"name": "Gives reasoned suggestion", "type": "min_length", "value": 80},
            ],
        },
    ]

    for i, turn_spec in enumerate(turns):
        turn_num = i + 1
        print(f"  Turn {turn_num}/3: {turn_spec['message'][:60]}...")

        response, duration = engine.chat(turn_spec["message"])
        checks = engine.evaluate(response, turn_spec["checks"])

        turn = TurnResult(
            turn_number=turn_num,
            user_message=turn_spec["message"],
            bot_response=response,
            duration_seconds=duration,
            checks=checks,
        )
        result.turns.append(turn)

        for check in checks:
            icon = "✅" if check["verdict"] == Verdict.PASS else "❌"
            print(f"    {icon} {check['name']}: {check['detail'][:80]}")

        if i < len(turns) - 1:
            time.sleep(2)

    all_passed = all(t.passed_all for t in result.turns)
    result.verdict = Verdict.PASS if all_passed else Verdict.PARTIAL
    result.summary = "Natural, continuous conversation with project recall" if all_passed else "Partial continuity"
    result.duration_seconds = time.time() - start
    return result


# ============================================================================
# Reporter
# ============================================================================

def print_report(results: List[ScenarioResult]):
    """Print a comprehensive test report."""
    print("\n" + "=" * 70)
    print("🧠 BRAIN TUNER — Conversation Intelligence Report")
    print("=" * 70)
    print(f"  Timestamp: {datetime.now().isoformat()}")
    print(f"  Scenarios: {len(results)}")
    print()

    total_checks = 0
    passed_checks = 0
    scenario_verdicts = []

    for result in results:
        icon = {"PASS": "✅", "FAIL": "❌", "PARTIAL": "⚠️", "ERROR": "💥"}[result.verdict.value]
        print(f"  {icon} {result.scenario_name} ({result.duration_seconds:.1f}s)")
        print(f"     {result.summary}")
        print(f"     Checks: {result.passed_checks}/{result.total_checks} passed")

        total_checks += result.total_checks
        passed_checks += result.passed_checks
        scenario_verdicts.append(result.verdict)

        # Show failed checks
        for turn in result.turns:
            for check in turn.checks:
                if check["verdict"] != Verdict.PASS:
                    print(f"     ❌ Turn {turn.turn_number}: {check['name']} — {check['detail'][:60]}")

        print()

    # Overall summary
    all_pass = all(v == Verdict.PASS for v in scenario_verdicts)
    any_fail = any(v == Verdict.FAIL for v in scenario_verdicts)

    print("=" * 70)
    if all_pass:
        print("🎉 ALL SCENARIOS PASSED — Brain Assistant is conversationally intelligent!")
    elif any_fail:
        print("❌ FAILURES DETECTED — Conversation intelligence needs work")
    else:
        print("⚠️  PARTIAL — Some scenarios need improvement")

    print(f"   Total checks: {passed_checks}/{total_checks} passed")
    print("=" * 70)

    return all_pass


def save_report(results: List[ScenarioResult], path: str):
    """Save report as JSON."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "scenarios": [],
    }

    for result in results:
        scenario = {
            "name": result.scenario_name,
            "verdict": result.verdict.value,
            "summary": result.summary,
            "duration_seconds": result.duration_seconds,
            "checks_passed": result.passed_checks,
            "checks_total": result.total_checks,
            "turns": [],
        }
        for turn in result.turns:
            t = {
                "turn": turn.turn_number,
                "user": turn.user_message,
                "bot": turn.bot_response[:500],
                "duration": turn.duration_seconds,
                "checks": [
                    {"name": c["name"], "verdict": c["verdict"].value, "detail": c["detail"]}
                    for c in turn.checks
                ],
            }
            scenario["turns"].append(t)
        report["scenarios"].append(scenario)

    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n📄 Report saved to: {path}")


# ============================================================================
# Main
# ============================================================================

SCENARIOS = {
    "name-recall": scenario_name_recall,
    "context-vs-search": scenario_context_vs_search,
    "personality": scenario_personality_continuity,
}


def main():
    parser = argparse.ArgumentParser(
        description="Brain Tuner — Dynamic conversation testing for Brain Assistant"
    )
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()) + ["all"],
        default="name-recall",
        help="Scenario to run (default: name-recall)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full bot responses")
    parser.add_argument("--timeout", type=int, default=90, help="Response timeout in seconds")
    parser.add_argument("--report", type=str, default=None, help="Save JSON report to file")

    args = parser.parse_args()

    print("\n🧠 Brain Tuner — Conversation Intelligence Testing")
    print(f"   Scenario: {args.scenario}")
    print(f"   Timeout:  {args.timeout}s")
    print()

    engine = ConversationEngine(verbose=args.verbose, timeout=args.timeout)

    # Determine which scenarios to run
    if args.scenario == "all":
        scenario_funcs = list(SCENARIOS.items())
    else:
        scenario_funcs = [(args.scenario, SCENARIOS[args.scenario])]

    results = []
    for name, func in scenario_funcs:
        print(f"\n🔬 Scenario: {name}")
        print("-" * 50)
        result = func(engine)
        results.append(result)

    all_pass = print_report(results)

    if args.report:
        save_report(results, args.report)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
