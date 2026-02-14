"""
Agent Platform - Core framework for running autonomous agents on NUC-2
"""

import asyncio
import logging
import sys
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from pathlib import Path
import yaml
import json

# Add clients to path
sys.path.insert(0, str(Path(__file__).parent / "clients"))

from khoj_client import KhojClient
from llm_client import OllamaClient
from brain_io import BrainIO

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "logs" / "agent_platform.log")
    ]
)

logger = logging.getLogger(__name__)


class Agent:
    """Base class for all agents"""

    def __init__(
        self,
        name: str,
        khoj: Optional[KhojClient] = None,
        llm: Optional[OllamaClient] = None,
        brain_io: Optional[BrainIO] = None,
    ):
        self.name = name
        self.khoj = khoj or KhojClient()
        self.llm = llm or OllamaClient()
        self.brain_io = brain_io or BrainIO()
        self.start_time = None
        self.end_time = None
        self.logger = logging.getLogger(self.name)

    async def run(self) -> bool:
        """
        Main agent execution. Override in subclass.
        
        Returns:
            True if successful, False otherwise
        """
        raise NotImplementedError("Subclass must implement run()")

    async def execute(self) -> bool:
        """Execute the agent with timing and error handling"""
        self.start_time = datetime.now()
        logger.info(f"[{self.name}] Starting execution...")
        
        try:
            result = await self.run()
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()
            
            status = "✓ SUCCESS" if result else "✗ FAILED"
            logger.info(f"[{self.name}] {status} (took {duration:.2f}s)")
            
            return result
            
        except Exception as e:
            self.end_time = datetime.now()
            duration = (self.end_time - self.start_time).total_seconds()
            logger.error(f"[{self.name}] ✗ ERROR: {e} (took {duration:.2f}s)", exc_info=True)
            return False

    async def notify(self, title: str, message: str, priority: str = "default"):
        """Send a notification via the notification system"""
        import subprocess
        try:
            subprocess.run([
                "/usr/local/bin/notify.sh",
                title,
                message,
                priority
            ], check=False)
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")

    async def log_execution(self, result: bool, details: str = ""):
        """Log execution to a JSON file in logs folder"""
        log_file = Path(__file__).parent / "logs" / f"{self.name}_executions.jsonl"
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.name,
            "success": result,
            "duration": (self.end_time - self.start_time).total_seconds() if self.end_time else 0,
            "details": details,
        }
        
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log execution: {e}")


class AgentPlatform:
    """Platform for registering and running agents"""

    def __init__(self):
        self.agents: Dict[str, Callable] = {}
        self.khoj = KhojClient()
        self.llm = OllamaClient()
        self.brain_io = BrainIO()

    def register_agent(self, name: str, agent_class: type):
        """Register an agent class"""
        self.agents[name] = agent_class
        logger.info(f"Registered agent: {name}")

    async def run_agent(self, name: str, **kwargs) -> bool:
        """Run a specific agent"""
        if name not in self.agents:
            logger.error(f"Unknown agent: {name}")
            return False
        
        agent_class = self.agents[name]
        agent = agent_class(
            name=name,
            khoj=self.khoj,
            llm=self.llm,
            brain_io=self.brain_io,
            **kwargs
        )
        
        return await agent.execute()

    async def start_service(self, agent: "Agent") -> None:
        """
        Start a long-running service agent (runs indefinitely)
        
        Used for agents like SlackAgent that need to stay running and listen for events.
        Handles errors and notifications, with automatic restart on failure.
        
        Args:
            agent: Agent instance to run as service
        """
        logger.info(f"Starting service agent: {agent.name}")
        
        max_restarts = 5
        restart_count = 0
        base_delay = 5
        
        while restart_count < max_restarts:
            try:
                # Run the agent's main loop (blocks indefinitely)
                await agent.run()
                
                # If we get here, agent stopped gracefully
                logger.info(f"Service agent {agent.name} stopped gracefully")
                break
                
            except KeyboardInterrupt:
                logger.info(f"Service agent {agent.name} interrupted by user")
                break
                
            except Exception as e:
                restart_count += 1
                delay = base_delay * restart_count
                
                logger.error(
                    f"Service agent {agent.name} crashed (attempt {restart_count}/{max_restarts}): {e}",
                    exc_info=True
                )
                
                # Send notification
                try:
                    await agent.notify(
                        f"⚠️ Service agent {agent.name} crashed (restart {restart_count}/{max_restarts}): {e}"
                    )
                except:
                    pass
                
                if restart_count < max_restarts:
                    logger.info(f"Restarting in {delay} seconds...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Service agent {agent.name} exceeded max restarts, giving up")
                    try:
                        await agent.notify(
                            f"❌ Service agent {agent.name} failed permanently after {max_restarts} restart attempts"
                        )
                    except:
                        pass
                    raise

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all dependencies"""
        health = {
            "khoj": await self.khoj.health_check(),
            "ollama": await self.llm.health_check(),
            "brain_path": self.brain_io.get_brain_path().exists(),
        }
        
        logger.info(f"Health check: {health}")
        return health

    async def close(self):
        """Close all connections"""
        await self.khoj.close()
        await self.llm.close()


# Global platform instance
platform = AgentPlatform()


async def main():
    """Main entry point for platform"""
    # Register built-in agents
    from agents.journal_agent import JournalAgent
    from agents.advice_agent import AdviceAgent
    
    platform.register_agent("journal", JournalAgent)
    platform.register_agent("advice", AdviceAgent)
    
    # Check health
    health = await platform.health_check()
    logger.info(f"System health: {health}")
    
    if not all(health.values()):
        logger.error("System health check failed!")
        return False
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        agent_name = sys.argv[1]
        result = await platform.run_agent(agent_name)
    else:
        logger.info("Usage: python -m agent_platform [agent_name]")
        result = False
    
    await platform.close()
    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
