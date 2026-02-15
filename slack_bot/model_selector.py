"""
Slack Block Kit UI builder for model selection.

Provides helper functions for the /model command UI.
"""

from typing import List, Dict
from services.model_manager import ModelManager


def build_model_selector_ui(manager: ModelManager) -> List[Dict]:
    """
    Build Block Kit UI for model selection.

    Args:
        manager: ModelManager instance

    Returns:
        list: Block Kit blocks for the UI
    """
    blocks = []

    # Current config section
    config = manager.get_current_config()
    if config["provider_id"]:
        status_text = (
            f"*Current Selection:* 🟢 {config['provider_name']} "
            f"(`{config['model_name']}`)\n"
            f"_Note: Phase 1 - Selection is saved but not yet used for inference_"
        )
    else:
        status_text = (
            "*Current Selection:* ⚪ No model selected\n"
            f"_Note: Bot is using default Ollama model. Selection here is for future use._"
        )

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": status_text}})

    blocks.append({"type": "divider"})

    # Provider selection
    available_providers = manager.get_available_providers()

    if not available_providers:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ No providers available. Check API keys or Ollama connection.",
                },
            }
        )
        return blocks

    # Provider dropdown
    provider_options = []
    for provider in available_providers:
        provider_options.append(
            {
                "text": {"type": "plain_text", "text": provider["name"]},
                "value": provider["id"],
            }
        )

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Select Provider:*"},
            "accessory": {
                "type": "static_select",
                "action_id": "select_provider",
                "placeholder": {"type": "plain_text", "text": "Choose provider..."},
                "options": provider_options,
            },
        }
    )

    # Model dropdown - show filtered models from all providers
    model_options = []
    for provider in available_providers:
        # Filter models based on provider type
        models = provider["models"]

        # For Ollama providers, only show llama models
        if "ollama" in provider["id"].lower():
            models = [m for m in models if "llama" in m.lower()]

        # Add models with shortened names to avoid overflow
        for model in models[:5]:  # Limit to 5 models per provider
            # Shorten provider name for display
            provider_short = provider['name'].replace("Ollama ", "").replace(" - ", " ")

            # Shorten model name if too long
            model_display = model[:30] + "..." if len(model) > 30 else model

            model_options.append(
                {
                    "text": {
                        "type": "plain_text",
                        "text": f"{provider_short}: {model_display}",
                    },
                    "value": f"{provider['id']}:{model}",
                }
            )

    if model_options:
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Select Model:*"},
                "accessory": {
                    "type": "static_select",
                    "action_id": "select_model",
                    "placeholder": {"type": "plain_text", "text": "Choose model..."},
                    "options": model_options[:25],  # Slack limits to 100 options
                },
            }
        )
    else:
        # No models available
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ No compatible models found. Install llama models on your Ollama servers.",
                },
            }
        )

    return blocks


def get_models_for_provider(manager: ModelManager, provider_id: str) -> List[str]:
    """
    Get list of models for a specific provider.

    Args:
        manager: ModelManager instance
        provider_id: Provider ID

    Returns:
        list: List of model names
    """
    if provider_id not in manager.providers:
        return []

    provider = manager.providers[provider_id]
    return provider.list_models()


def apply_model_selection(
    manager: ModelManager, provider_id: str, model_name: str
) -> Dict:
    """
    Apply model selection and update manager state.

    Args:
        manager: ModelManager instance
        provider_id: Provider ID to use
        model_name: Model name to use

    Returns:
        dict: Result with 'success' bool and optional 'error' message
    """
    try:
        manager.set_model(provider_id, model_name)
        return {
            "success": True,
            "provider_id": provider_id,
            "model_name": model_name,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
