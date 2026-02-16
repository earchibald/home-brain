#!/usr/bin/env python3
"""
Slack Bot Launcher - Entry point for Slack agent service

Loads configuration, initializes SlackAgent, and starts the service.
Designed to run as systemd service or standalone for testing.
"""

import os
import sys
import signal
import asyncio
from pathlib import Path
from typing import Optional

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from agent_platform import AgentPlatform
from agents.slack_agent import SlackAgent


class SlackBotService:
    """Service wrapper for Slack bot"""

    def __init__(self):
        self.platform = AgentPlatform()
        self.agent: Optional[SlackAgent] = None
        self.shutdown_event = asyncio.Event()

    def load_secrets(self):
        """Load secrets from secrets.env file"""
        # If Slack tokens are already in environment (e.g., from sops wrapper), skip loading
        if os.getenv("SLACK_BOT_TOKEN") and os.getenv("SLACK_APP_TOKEN"):
            print("📝 Using Slack tokens from environment (already decrypted)")
            return

        secrets_file = Path(__file__).parent / "secrets.env"

        if not secrets_file.exists():
            print(f"⚠️  secrets.env not found at {secrets_file}")
            print("   Assuming environment variables are already set...")
            return

        print(f"📝 Loading secrets from {secrets_file}")

        with open(secrets_file) as f:
            for line in f:
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith("#"):
                    continue

                # Skip SOPS encrypted lines
                if "ENC[" in line:
                    continue

                # Parse: export KEY="value" or KEY=value
                if "=" not in line:
                    continue

                if line.startswith("export "):
                    line = line[7:]

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                # Only set if not already in environment (env vars take precedence)
                if key not in os.environ:
                    os.environ[key] = value

    def validate_environment(self):
        """Validate required environment variables"""
        required = [
            "SLACK_BOT_TOKEN",
            "SLACK_APP_TOKEN",
        ]

        optional = {
            "SEARCH_URL": "http://nuc-1.local:9514",
            "OLLAMA_URL": "http://m1-mini.local:11434",
            "BRAIN_FOLDER": "/home/earchibald/brain",
            "NTFY_TOPIC": "brain-notifications",
        }

        missing = []
        for var in required:
            if not os.getenv(var):
                missing.append(var)

        if missing:
            print(f"❌ Missing required environment variables: {', '.join(missing)}")
            print("\nRequired variables:")
            print("  SLACK_BOT_TOKEN   - Bot token from api.slack.com (xoxb-...)")
            print("  SLACK_APP_TOKEN   - App token for Socket Mode (xapp-...)")
            print("\nOptional variables (with defaults):")
            for var, default in optional.items():
                print(f"  {var:20s} - {default}")
            sys.exit(1)

        # Set defaults for optional vars
        for var, default in optional.items():
            if not os.getenv(var):
                os.environ[var] = default

        # Print configuration
        print("\n✅ Configuration:")
        print(f"   Search: {os.getenv('SEARCH_URL')}")
        print(f"   Ollama:  {os.getenv('OLLAMA_URL')}")
        print(f"   Brain:   {os.getenv('BRAIN_FOLDER')}")
        print(f"   Notify:  ntfy.sh/{os.getenv('NTFY_TOPIC')}")
        print(f"   Bot:     {os.getenv('SLACK_BOT_TOKEN')[:20]}...")
        print()

    def setup_signals(self):
        """Setup signal handlers for graceful shutdown"""

        def signal_handler(signum, frame):
            print(f"\n📡 Received signal {signum}, shutting down gracefully...")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def run(self):
        """Main service loop"""
        # Load secrets
        self.load_secrets()

        # Validate environment
        self.validate_environment()

        # Setup signals
        self.setup_signals()

        # Create agent configuration
        config = {
            "search_url": os.getenv("SEARCH_URL"),
            "ollama_url": os.getenv("OLLAMA_URL"),
            "brain_path": os.getenv("BRAIN_FOLDER"),
            "model": os.getenv("SLACK_MODEL", "llama3.2"),
            "max_context_tokens": int(os.getenv("SLACK_MAX_CONTEXT_TOKENS", "6000")),
            "enable_search": os.getenv("SLACK_ENABLE_SEARCH", "true").lower()
            == "true",
            "max_search_results": int(os.getenv("SLACK_MAX_SEARCH_RESULTS", "3")),
            "enable_model_switching": os.getenv("ENABLE_MODEL_SWITCHING", "true").lower()
            == "true",
            "enable_web_search": os.getenv("ENABLE_WEB_SEARCH", "true").lower()
            == "true",
            "web_search_provider": os.getenv("WEB_SEARCH_PROVIDER", "duckduckgo"),
            "tavily_api_key": os.getenv("TAVILY_API_KEY"),
            "notification": {"enabled": True, "topic": os.getenv("NTFY_TOPIC")},
        }

        # Initialize agent
        print("🤖 Initializing Slack agent...")
        self.agent = SlackAgent(config)

        # Start service
        print("🚀 Starting Slack bot service...\n")

        try:
            # Run service (blocks indefinitely)
            service_task = asyncio.create_task(self.platform.start_service(self.agent))

            # Wait for shutdown signal
            shutdown_task = asyncio.create_task(self.shutdown_event.wait())

            # Wait for either service to fail or shutdown signal
            done, pending = await asyncio.wait(
                [service_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            # Check if service failed
            if service_task in done:
                # Service stopped/crashed, check for exception
                try:
                    service_task.result()
                except Exception as e:
                    print(f"❌ Service failed: {e}")
                    raise

            print("\n👋 Slack bot service stopped gracefully")

        except KeyboardInterrupt:
            print("\n👋 Interrupted by user")

        except Exception as e:
            print(f"\n❌ Fatal error: {e}")
            raise

        finally:
            # Cleanup
            print("🧹 Cleaning up...")
            await self.platform.close()


def main():
    """Entry point"""
    print("=" * 60)
    print("  Slack Bot Service for Semantic Brain")
    print("=" * 60)
    print()

    service = SlackBotService()

    try:
        asyncio.run(service.run())
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Service crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
