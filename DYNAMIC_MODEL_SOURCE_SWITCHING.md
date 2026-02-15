# **Implementation Specification: Dynamic Model Source Switching**

## **1\. Overview**

This feature allows the Slack bot to dynamically switch its LLM backend at runtime without restarting. It supports local Ollama instances (Mac Mini, MacBook Pro) and cloud APIs (Gemini, Anthropic).

## **2\. Architecture: The Adapter Pattern**

The system uses a **Strategy/Adapter Pattern**. The main bot logic communicates with a ModelManager, which delegates actual generation tasks to a specific LLMProvider.

### **2.1 Class Hierarchy**

* **BaseProvider (Abstract Base Class)**: Defines the contract.  
* **OllamaProvider**: Implementation for local/networked Ollama instances.  
* **GeminiProvider**: Implementation for Google's Gemini API.  
* **AnthropicProvider**: Implementation for Claude API.  
* **ModelManager**: Singleton service that holds the state of the *current* provider and handles discovery.

## **3\. Detailed Component Specifications**

### **3.1 Dependencies**

Required PyPI packages:  
slack\_bolt\>=1.18.0  
ollama\>=0.1.6  
google-generativeai\>=0.4.0  
anthropic\>=0.19.0  
requests\>=2.31.0

### **3.2 BaseProvider Interface**

**File:** src/providers/base.py  
from abc import ABC, abstractmethod

class BaseProvider(ABC):  
    id: str  \# Unique identifier (e.g., "ollama\_local", "gemini")  
    name: str \# Human readable name (e.g., "Mac Mini (Ollama)")

    @abstractmethod  
    def list\_models(self) \-\> list\[str\]:  
        """Returns a list of model identifiers available on this provider."""  
        pass

    @abstractmethod  
    def generate(self, prompt: str, system\_prompt: str \= None) \-\> str:  
        """Generates text based on input."""  
        pass

    @abstractmethod  
    def health\_check(self) \-\> bool:  
        """Quick check to see if provider is reachable."""  
        pass

### **3.3 OllamaProvider**

**File:** src/providers/ollama\_adapter.py

* **Constructor:** Accepts base\_url (string).  
* **Logic:**  
  * Uses ollama python library (configure Client(host=...)).  
  * list\_models: Calls /api/tags.  
  * health\_check: Simple GET request to root / or /api/version with a short timeout (1s).  
* **Instances to Create:**  
  1. **Mac Mini (Host):** base\_url="http://localhost:11434" (Default).  
  2. **MacBook Pro (Remote):** base\_url="http://eugenes-mbp.local:11434".

### **3.4 GeminiProvider**

**File:** src/providers/gemini\_adapter.py

* **Auth:** Checks os.environ\["GOOGLE\_API\_KEY"\].  
* **Logic:** Uses google.generativeai.  
* **Models:** Hardcoded list for now (or dynamic if API supports) \-\> \["gemini-1.5-pro", "gemini-1.5-flash"\].

### **3.5 AnthropicProvider**

**File:** src/providers/anthropic\_adapter.py

* **Auth:** Checks os.environ\["ANTHROPIC\_API\_KEY"\].  
* **Logic:** Uses anthropic.Anthropic().  
* **Models:** \["claude-3-5-sonnet-latest", "claude-3-opus-latest"\].

## **4\. The Model Manager Logic**

**File:** src/services/model\_manager.py  
The manager acts as the "State Machine".

### **4.1 Properties**

* providers: Dictionary of {provider\_id: BaseProvider instance}.  
* current\_provider\_id: String.  
* current\_model\_name: String.

### **4.2 Discovery Logic (discover\_available\_sources)**

Executed on startup and when user requests /model list.

1. **Check Local:** Ping localhost:11434. If success, add to available.  
2. **Check Remote:** Ping eugenes-mbp.local:11434 (Timeout: 1s). If success, add to available.  
3. **Check Cloud:** Check if API keys exist in ENV. If yes, add to available.

### **4.3 Switching Logic (set\_model)**

* Updates current\_provider\_id and current\_model\_name.  
* Persists this preference in-memory (Phase 1\) or SQLite/JSON (Phase 2).

## **5\. Slack Interface (Block Kit)**

### **5.1 Slash Command: /model**

**Handler:**

1. Triggers manager.discover\_available\_sources().  
2. Constructs a Block Kit message (Ephemeral).

### **5.2 UI Layout (JSON Payload Structure)**

The UI should present two dropdowns:

1. **Provider Select:** Triggers an action to reload the Model Select.  
2. **Model Select:** The actual switching trigger.

**Block Kit Structure:**  
\[  
  {  
    "type": "section",  
    "text": { "type": "mrkdwn", "text": "\*Current Config:\* 🟢 Mac Mini (\`llama3.2\`)" }  
  },  
  {  
    "type": "divider"  
  },  
  {  
    "type": "section",  
    "text": { "type": "mrkdwn", "text": "Select Provider:" },  
    "accessory": {  
      "type": "static\_select",  
      "action\_id": "select\_provider",  
      "options": \[  
        { "text": { "type": "plain\_text", "text": "Mac Mini (Local)" }, "value": "ollama\_local" },  
        { "text": { "type": "plain\_text", "text": "Eugene's MBP" }, "value": "ollama\_remote" },  
        { "text": { "type": "plain\_text", "text": "Gemini API" }, "value": "gemini" }  
      \]  
    }  
  },  
  {  
    "type": "section",  
    "text": { "type": "mrkdwn", "text": "Select Model:" },  
    "accessory": {  
      "type": "static\_select",  
      "action\_id": "select\_model",  
      "options": \[ ...dynamic list based on provider... \]  
    }  
  }  
\]

## **6\. Environment Variables (.env)**

SLACK\_BOT\_TOKEN=xoxb-...  
SLACK\_APP\_TOKEN=xapp-...  
GOOGLE\_API\_KEY=AIza...  
ANTHROPIC\_API\_KEY=sk-ant...  
\# Optional: Overrides for hostnames  
OLLAMA\_HOST\_LOCAL=http://localhost:11434  
OLLAMA\_HOST\_REMOTE=\[http://eugenes-mbp.local:11434\](http://eugenes-mbp.local:11434)

## **7\. Execution Plan**

1. **Scaffold:** Create BaseProvider and the folder structure.  
2. **Adapters:** Implement OllamaProvider first, then Gemini/Anthropic.  
3. **Manager:** Implement ModelManager with the health check logic.  
4. **Integration:** Modify the main app\_mention or message handler in bot.py to use model\_manager.generate() instead of the direct Ollama call.  
5. **UI:** Implement the /model command and the block\_actions handler for the dropdowns.