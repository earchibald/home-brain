# **Omnibus: Slack Assistant Framework Migration**

## **1\. Objective**

Migrate the existing "Old School" Slack bot to the new **Slack Assistant Framework**. This involves enabling the split-view UI, managing "Thinking..." states via native APIs, and injecting user context (focused channel) into the LLM prompts.

## **2\. Implementation Strategy**

We will modify four core files. The code provided below is the **complete** file content, ready to replace the existing versions.

1. **clients/conversation\_manager.py**: Add state tracking for "Assistant Context" (what channel the user is viewing).  
2. **slack\_bot/slack\_message\_updater.py**: Add wrappers for assistant.threads.setStatus, setTitle, and setSuggestedPrompts.  
3. **slack\_bot/message\_processor.py**: Refactor to use setStatus instead of sending temporary messages, and prepend context to prompts.  
4. **slack\_bot.py**: Register event listeners for assistant\_thread\_started and assistant\_thread\_context\_changed.

## **3\. File Updates**

### **File 1: clients/conversation\_manager.py**

**Change:** Added assistant\_contexts storage and methods to save/retrieve the user's focused channel context.  
import logging  
import time  
from typing import Dict, List, Optional, Any

logger \= logging.getLogger(\_\_name\_\_)

class ConversationManager:  
    """  
    Manages conversation history and context for users/threads.  
    Now supports Slack Assistant context awareness.  
    """  
    def \_\_init\_\_(self):  
        \# Existing history storage  
        \# Key: f"{channel\_id}:{user\_id}" (Legacy) or f"{channel\_id}:{thread\_ts}" (Thread-based)  
        self.history: Dict\[str, List\[Dict\[str, Any\]\]\] \= {}  
          
        \# New: Store context for Assistant threads (e.g., what channel user is looking at)  
        \# Key: f"{channel\_id}:{thread\_ts}" \-\> Value: Context Dictionary  
        self.assistant\_contexts: Dict\[str, Dict\[str, Any\]\] \= {}  
          
        \# New: Track which threads are "Assistant" threads vs standard DMs  
        self.assistant\_threads: set \= set()

    def \_get\_key(self, channel\_id: str, user\_id: str) \-\> str:  
        \# Note: Depending on your specific bot logic, this key strategy might vary.  
        \# This implementation assumes channel+user uniqueness for history.  
        return f"{channel\_id}:{user\_id}"

    def update\_conversation\_history(self, channel\_id: str, user\_id: str, role: str, content: str):  
        """  
        Updates the conversation history for a specific user in a channel.  
        """  
        key \= self.\_get\_key(channel\_id, user\_id)  
        if key not in self.history:  
            self.history\[key\] \= \[\]  
          
        self.history\[key\].append({  
            "role": role,  
            "content": content,  
            "timestamp": time.time()  
        })  
          
        \# Limit history to last 20 messages to prevent context overflow  
        if len(self.history\[key\]) \> 20:  
            self.history\[key\] \= self.history\[key\]\[-20:\]

    def get\_conversation\_history(self, channel\_id: str, user\_id: str) \-\> List\[Dict\[str, Any\]\]:  
        """  
        Retrieves the conversation history for a specific user in a channel.  
        """  
        key \= self.\_get\_key(channel\_id, user\_id)  
        return self.history.get(key, \[\])

    def clear\_history(self, channel\_id: str, user\_id: str):  
        """  
        Clears conversation history.  
        """  
        key \= self.\_get\_key(channel\_id, user\_id)  
        if key in self.history:  
            del self.history\[key\]  
            logger.info(f"Cleared history for {key}")

    \# \--- Assistant Framework Methods \---

    def mark\_as\_assistant\_thread(self, channel\_id: str, thread\_ts: str):  
        """  
        Marks a specific thread as being part of the Assistant UI surface.  
        """  
        if not thread\_ts:  
            return  
        key \= f"{channel\_id}:{thread\_ts}"  
        self.assistant\_threads.add(key)  
        logger.info(f"Marked thread {key} as Assistant thread")

    def is\_assistant\_thread(self, channel\_id: str, thread\_ts: str) \-\> bool:  
        """  
        Checks if a thread is an Assistant thread.  
        """  
        if not thread\_ts:  
            return False  
        key \= f"{channel\_id}:{thread\_ts}"  
        return key in self.assistant\_threads

    def save\_assistant\_context(self, channel\_id: str, thread\_ts: str, context: Dict\[str, Any\]):  
        """  
        Saves the context (e.g. focused channel) provided by the assistant\_thread\_context\_changed event.  
        """  
        if not thread\_ts:  
            return  
        key \= f"{channel\_id}:{thread\_ts}"  
        self.assistant\_contexts\[key\] \= context  
        logger.debug(f"Updated context for {key}: {context}")

    def get\_assistant\_context(self, channel\_id: str, thread\_ts: str) \-\> Optional\[Dict\[str, Any\]\]:  
        """  
        Retrieves the current context for an assistant thread.  
        """  
        if not thread\_ts:  
            return None  
        key \= f"{channel\_id}:{thread\_ts}"  
        return self.assistant\_contexts.get(key)

### **File 2: slack\_bot/slack\_message\_updater.py**

**Change:** Added methods set\_assistant\_status, set\_assistant\_title, and set\_suggested\_prompts.  
import logging  
from slack\_sdk import WebClient  
from slack\_sdk.errors import SlackApiError

logger \= logging.getLogger(\_\_name\_\_)

class SlackMessageUpdater:  
    """  
    Handles sending and updating messages in Slack.  
    Now supports Assistant Framework specific methods (setStatus, setTitle, SuggestedPrompts).  
    """  
    def \_\_init\_\_(self, client: WebClient):  
        self.client \= client

    def send\_initial\_message(self, channel\_id: str, text: str, thread\_ts: str \= None) \-\> str:  
        """  
        Sends the initial message (e.g., "Thinking...") and returns its timestamp.  
        Used for standard bot interactions.  
        """  
        try:  
            response \= self.client.chat\_postMessage(  
                channel=channel\_id,  
                text=text,  
                thread\_ts=thread\_ts  
            )  
            return response\["ts"\]  
        except SlackApiError as e:  
            logger.error(f"Error sending initial message: {e}")  
            raise e

    def update\_message(self, channel\_id: str, ts: str, text: str):  
        """  
        Updates an existing message with new text.  
        """  
        try:  
            self.client.chat\_update(  
                channel=channel\_id,  
                ts=ts,  
                text=text  
            )  
        except SlackApiError as e:  
            logger.error(f"Error updating message: {e}")

    def send\_final\_message(self, channel\_id: str, thread\_ts: str, text: str):  
        """  
        Sends a final new message instead of updating an existing one.  
        Useful if streaming/thinking was handled via status, not a placeholder msg.  
        """  
        try:  
            self.client.chat\_postMessage(  
                channel=channel\_id,  
                text=text,  
                thread\_ts=thread\_ts  
            )  
        except SlackApiError as e:  
            logger.error(f"Error sending final message: {e}")

    def send\_error\_message(self, channel\_id: str, thread\_ts: str, text: str):  
        """  
        Sends an error message.  
        """  
        try:  
            self.client.chat\_postMessage(  
                channel=channel\_id,  
                text=f":warning: {text}",  
                thread\_ts=thread\_ts  
            )  
        except SlackApiError as e:  
            logger.error(f"Error sending error message: {e}")

    \# \--- Assistant Framework Methods \---

    def set\_assistant\_status(self, channel\_id: str, thread\_ts: str, status: str):  
        """  
        Sets the 'Thinking...' status for an Assistant thread.  
        This replaces the need for a temporary 'Thinking...' message.  
        """  
        try:  
            self.client.assistant\_threads\_setStatus(  
                channel\_id=channel\_id,  
                thread\_ts=thread\_ts,  
                status=status  
            )  
        except SlackApiError as e:  
            logger.error(f"Error setting assistant status: {e}")

    def set\_assistant\_title(self, channel\_id: str, thread\_ts: str, title: str):  
        """  
        Renames the Assistant thread.  
        """  
        try:  
            self.client.assistant\_threads\_setTitle(  
                channel\_id=channel\_id,  
                thread\_ts=thread\_ts,  
                title=title  
            )  
        except SlackApiError as e:  
            logger.error(f"Error setting assistant title: {e}")

    def set\_suggested\_prompts(self, channel\_id: str, thread\_ts: str, prompts: list):  
        """  
        Sets the quick-start prompts for the thread.  
        prompts \= \[{'title': '...', 'message': '...'}\]  
        """  
        try:  
            self.client.assistant\_threads\_setSuggestedPrompts(  
                channel\_id=channel\_id,  
                thread\_ts=thread\_ts,  
                prompts=prompts  
            )  
        except SlackApiError as e:  
            logger.error(f"Error setting suggested prompts: {e}")

### **File 3: slack\_bot/message\_processor.py**

**Change:** process\_message now accepts is\_assistant and assistant\_context. It branches logic to use set\_assistant\_status and injects context into the prompt.  
import logging  
import time  
from typing import Optional, Dict, Any  
from slack\_sdk import WebClient  
from slack\_bot.slack\_message\_updater import SlackMessageUpdater  
from clients.conversation\_manager import ConversationManager  
from slack\_bot.model\_selector import ModelSelector  
from slack\_bot.streaming\_handler import StreamingHandler  
from slack\_bot.performance\_monitor import PerformanceMonitor  
from slack\_bot.alerting import AlertManager

logger \= logging.getLogger(\_\_name\_\_)

class MessageProcessor:  
    """  
    Orchestrates the processing of incoming messages:  
    1\. Manages UI state (Thinking vs Status)  
    2\. Selects Model  
    3\. Generates Response  
    4\. Updates UI  
    """  
    def \_\_init\_\_(  
        self,   
        client: WebClient,   
        conversation\_manager: ConversationManager,  
        model\_selector: ModelSelector,  
        alert\_manager: AlertManager  
    ):  
        self.client \= client  
        self.conversation\_manager \= conversation\_manager  
        self.model\_selector \= model\_selector  
        self.message\_updater \= SlackMessageUpdater(client)  
        self.streaming\_handler \= StreamingHandler(self.message\_updater)  
        self.performance\_monitor \= PerformanceMonitor(alert\_manager)

    def process\_message(  
        self,   
        text: str,   
        channel\_id: str,   
        user\_id: str,   
        thread\_ts: str \= None,   
        is\_assistant: bool \= False,  
        assistant\_context: Optional\[Dict\[str, Any\]\] \= None  
    ):  
        """  
        Main entry point for processing a user message.  
        """  
        start\_time \= time.time()  
          
        \# 1\. Update Conversation History  
        self.conversation\_manager.update\_conversation\_history(channel\_id, user\_id, "user", text)  
        history \= self.conversation\_manager.get\_conversation\_history(channel\_id, user\_id)

        \# 2\. Prepare Prompt with Context (if available)  
        final\_prompt \= text  
        if is\_assistant and assistant\_context:  
            \# Inject context about what the user is looking at  
            context\_info \= \[\]  
            if assistant\_context.get('channel\_id'):  
                context\_info.append(f"The user is currently viewing channel ID: {assistant\_context\['channel\_id'\]}")  
            if assistant\_context.get('team\_id'):  
                context\_info.append(f"Team ID: {assistant\_context\['team\_id'\]}")  
              
            if context\_info:  
                system\_context \= "\\n\[System Context: " \+ "; ".join(context\_info) \+ "\]\\n"  
                final\_prompt \= system\_context \+ text  
                logger.info(f"Injected context into prompt for thread {thread\_ts}")

        \# 3\. UI Feedback: Managed State vs Legacy Message  
        temp\_ts \= None  
        if is\_assistant:  
            \# Use new Assistant API \- No visible "message" created yet  
            self.message\_updater.set\_assistant\_status(  
                channel\_id=channel\_id,   
                thread\_ts=thread\_ts,   
                status="is thinking..."  
            )  
        else:  
            \# Legacy: Send "Thinking..." message  
            temp\_ts \= self.message\_updater.send\_initial\_message(channel\_id, "Thinking...", thread\_ts)

        try:  
            \# 4\. Generate & Stream Response  
            full\_response \= self.model\_selector.select\_model\_and\_generate(  
                prompt=final\_prompt,  
                history=history,  
                image\_data=None, \# Future: Support image inputs  
                callback=lambda chunk: self.streaming\_handler.handle\_chunk(  
                    chunk,   
                    channel\_id,   
                    temp\_ts, \# Only needed for legacy updates  
                    thread\_ts  
                )  
            )  
              
            \# 5\. Finalize UI  
            \# For Assistant, the status clears automatically when a message is posted.  
            \# If streaming handler didn't start (non-streaming model), we need to send the full message now.  
            if not self.streaming\_handler.stream\_started:  
                if is\_assistant:  
                     self.message\_updater.send\_final\_message(channel\_id, thread\_ts, full\_response)  
                else:  
                    \# Legacy: update the "Thinking..." placeholder or send new if it failed  
                    if temp\_ts:  
                        self.message\_updater.update\_message(channel\_id, temp\_ts, full\_response)  
                    else:  
                        self.message\_updater.send\_initial\_message(channel\_id, full\_response, thread\_ts)  
            else:  
                \# Streaming happened.  
                \# If legacy, ensure the final update is clean (sometimes chunks leave artifacts)  
                if not is\_assistant and temp\_ts:  
                    self.message\_updater.update\_message(channel\_id, temp\_ts, full\_response)  
              
            \# 6\. Post-Processing  
            self.conversation\_manager.update\_conversation\_history(channel\_id, user\_id, "assistant", full\_response)  
              
            \# Generate Title for Assistant Threads  
            if is\_assistant and thread\_ts:  
                \# Simple heuristic: Use first \~30 chars.   
                new\_title \= text\[:30\] \+ "..." if len(text) \> 30 else text  
                self.message\_updater.set\_assistant\_title(channel\_id, thread\_ts, new\_title)

            \# Record metrics  
            duration \= time.time() \- start\_time  
            self.performance\_monitor.record\_metric("response\_time", duration)

        except KeyboardInterrupt:  
            logger.warning("Message processing interrupted by user.")  
            pass  
              
        except Exception as e:  
            logger.error(f"Error processing message: {e}", exc\_info=True)  
            error\_msg \= "I encountered an error while processing your request."  
              
            if is\_assistant:  
                self.message\_updater.send\_error\_message(channel\_id, thread\_ts, error\_msg)  
            elif temp\_ts:  
                self.message\_updater.update\_message(channel\_id, temp\_ts, error\_msg)  
            else:  
                self.client.chat\_postMessage(channel=channel\_id, text=error\_msg, thread\_ts=thread\_ts)

### **File 4: slack\_bot.py**

**Change:** Added event handlers assistant\_thread\_started and assistant\_thread\_context\_changed. Updated handle\_message\_events to check for assistant status via ConversationManager.  
import os  
import logging  
from slack\_bolt import App  
from slack\_bolt.adapter.socket\_mode import SocketModeHandler  
from clients.conversation\_manager import ConversationManager  
from clients.cxdb\_client import CXDBClient  
from clients.vaultwarden\_client import VaultwardenClient  
from clients.llm\_client import LLMClient  
from slack\_bot.message\_processor import MessageProcessor  
from slack\_bot.model\_selector import ModelSelector  
from slack\_bot.alerting import AlertManager

\# Configure logging  
logging.basicConfig(level=logging.INFO)  
logger \= logging.getLogger(\_\_name\_\_)

\# Load environment variables  
SLACK\_BOT\_TOKEN \= os.environ.get("SLACK\_BOT\_TOKEN")  
SLACK\_APP\_TOKEN \= os.environ.get("SLACK\_APP\_TOKEN")  
SLACK\_SIGNING\_SECRET \= os.environ.get("SLACK\_SIGNING\_SECRET")

\# Initialize Bolt App  
app \= App(token=SLACK\_BOT\_TOKEN, signing\_secret=SLACK\_SIGNING\_SECRET)

\# Initialize Clients  
conversation\_manager \= ConversationManager()  
alert\_manager \= AlertManager()  
cxdb\_client \= CXDBClient()  
vaultwarden\_client \= VaultwardenClient()  
llm\_client \= LLMClient() 

\# Initialize Logic Components  
model\_selector \= ModelSelector(llm\_client, cxdb\_client)  
message\_processor \= MessageProcessor(  
    client=app.client,  
    conversation\_manager=conversation\_manager,  
    model\_selector=model\_selector,  
    alert\_manager=alert\_manager  
)

\# \--- Assistant Framework Event Handlers \---

@app.event("assistant\_thread\_started")  
def handle\_assistant\_thread\_started(event, client, logger):  
    """  
    Triggered when a user opens the Assistant view or starts a new thread.  
    We set up the 'suggested prompts' here.  
    """  
    try:  
        channel\_id \= event.get("channel\_id") or event.get("channel")  
        thread\_ts \= event.get("thread\_ts")  
        user\_id \= event.get("user\_id") or event.get("user")

        logger.info(f"Assistant thread started: {channel\_id}:{thread\_ts} by {user\_id}")  
          
        \# Mark this as an assistant thread for future reference  
        if channel\_id and thread\_ts:  
            conversation\_manager.mark\_as\_assistant\_thread(channel\_id, thread\_ts)

            \# Set suggested prompts to guide the user  
            message\_processor.message\_updater.set\_suggested\_prompts(  
                channel\_id=channel\_id,  
                thread\_ts=thread\_ts,  
                prompts=\[  
                    {"title": "Summarize Context", "message": "Summarize the channel I am currently looking at."},  
                    {"title": "Draft Response", "message": "Draft a polite response to the last message in this channel."},  
                    {"title": "Search Knowledge", "message": "Search the internal knowledge base for 'deployment'."},  
                    {"title": "Help", "message": "What capabilities do you have?"}  
                \]  
            )  
    except Exception as e:  
        logger.error(f"Failed to handle assistant\_thread\_started: {e}", exc\_info=True)

@app.event("assistant\_thread\_context\_changed")  
def handle\_assistant\_context\_changed(event, logger):  
    """  
    Triggered when the user switches context (e.g., changes channel) while the Assistant is open.  
    We save this context to inject it into the next prompt.  
    """  
    try:  
        channel\_id \= event.get("channel\_id") or event.get("channel")  
        thread\_ts \= event.get("thread\_ts")  
        context \= event.get("context", {}) \# Contains channel\_id, team\_id, enterprise\_id etc.  
          
        logger.info(f"Context changed for {channel\_id}:{thread\_ts} \-\> {context}")  
          
        if channel\_id and thread\_ts:  
            conversation\_manager.save\_assistant\_context(channel\_id, thread\_ts, context)  
    except Exception as e:  
        logger.error(f"Failed to handle assistant\_thread\_context\_changed: {e}", exc\_info=True)

\# \--- Standard Event Handlers \---

@app.event("message")  
def handle\_message\_events(body, logger, event):  
    """  
    Handles all message events. Checks if it's an Assistant thread or standard DM.  
    """  
    if event.get("bot\_id"):  
        return  \# Ignore bot's own messages

    user\_id \= event.get("user")  
    text \= event.get("text")  
    channel\_id \= event.get("channel")  
    thread\_ts \= event.get("thread\_ts") or event.get("ts") \# Use message ts if no thread exists yet

    \# Determine if this is an Assistant interaction  
    is\_assistant \= conversation\_manager.is\_assistant\_thread(channel\_id, thread\_ts)  
      
    \# Retrieve context if available  
    context \= None  
    if is\_assistant:  
        context \= conversation\_manager.get\_assistant\_context(channel\_id, thread\_ts)

    logger.info(f"Processing message in {channel\_id}, is\_assistant={is\_assistant}")

    message\_processor.process\_message(  
        text=text,  
        channel\_id=channel\_id,  
        user\_id=user\_id,  
        thread\_ts=thread\_ts,  
        is\_assistant=is\_assistant,  
        assistant\_context=context  
    )

@app.command("/brain")  
def handle\_slash\_command(ack, body, logger):  
    ack()  
    user\_id \= body\["user\_id"\]  
    text \= body\["text"\]  
    channel\_id \= body\["channel\_id"\]  
      
    \# Slash commands are legacy/standard interactions  
    message\_processor.process\_message(text, channel\_id, user\_id)

@app.event("app\_mention")  
def handle\_app\_mention(body, logger, event):  
    user\_id \= event\["user"\]  
    text \= event\["text"\]  
    channel\_id \= event\["channel"\]  
    thread\_ts \= event.get("thread\_ts")  
      
    \# Mentions are standard interactions  
    message\_processor.process\_message(text, channel\_id, user\_id, thread\_ts)

if \_\_name\_\_ \== "\_\_main\_\_":  
    handler \= SocketModeHandler(app, SLACK\_APP\_TOKEN)  
    handler.start()  
