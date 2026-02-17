"""
Slack Block Kit UI builder for model selection.

Provides helper functions for the /model command UI.
Supports dynamic provider-based model filtering.
"""

import logging
from typing import List, Dict, Optional
from services.model_manager import ModelManager

logger = logging.getLogger(__name__)


def build_model_selector_ui(
    manager: ModelManager,
    selected_provider_id: Optional[str] = None,
    gemini_configured: bool = False,
) -> List[Dict]:
    """
    Build Block Kit UI for model selection.

    Args:
        manager: ModelManager instance
        selected_provider_id: If set, only show models for this provider
        gemini_configured: Whether the current user has a Gemini API key

    Returns:
        list: Block Kit blocks for the UI
    """
    blocks = []

    # Current config section
    config = manager.get_current_config()
    if config["provider_id"]:
        status_text = (
            f"*Current Selection:* 🟢 {config['provider_name']} "
            f"(`{config['model_name']}`)"
        )
    else:
        # Get default provider name
        default_provider = manager.providers.get('ollama_configured')
        provider_name = default_provider.name if default_provider else 'Ollama'
        status_text = (
            f"*Current Selection:* ⚪ No model selected\n"
            f"_Using default: {provider_name} - llama3.2:latest_"
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

    # Provider dropdown with initial_option if provider is already selected
    provider_options = []
    initial_provider_option = None
    for provider in available_providers:
        option = {
            "text": {"type": "plain_text", "text": provider["name"]},
            "value": provider["id"],
        }
        provider_options.append(option)
        if selected_provider_id and provider["id"] == selected_provider_id:
            initial_provider_option = option

    provider_accessory = {
        "type": "static_select",
        "action_id": "select_provider",
        "placeholder": {"type": "plain_text", "text": "Choose provider..."},
        "options": provider_options,
    }
    if initial_provider_option:
        provider_accessory["initial_option"] = initial_provider_option

    blocks.append(
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Select Provider:*"},
            "accessory": provider_accessory,
        }
    )

    # Determine which providers to show models for
    if selected_provider_id:
        show_providers = [p for p in available_providers if p["id"] == selected_provider_id]
    else:
        show_providers = available_providers

    # Build model options for the selected (or all) providers
    model_options = []
    for provider in show_providers:
        models = provider["models"]

        # For Ollama providers, only show llama models
        if "ollama" in provider["id"].lower():
            models = [m for m in models if "llama" in m.lower()]

        # For Gemini, skip if user hasn't configured API key
        if provider["id"] == "gemini" and not gemini_configured:
            continue

        for model in models[:5]:
            provider_short = provider['name'].replace("Ollama ", "").replace(" - ", " ")
            model_display = model[:30] + "..." if len(model) > 30 else model

            model_options.append(
                {
                    "text": {
                        "type": "plain_text",
                        "text": f"{model_display} - {provider_short}",
                    },
                    "value": f"{provider['id']}:{model}",
                }
            )

    # Add Gemini API key prompt only if not configured
    if not gemini_configured and "gemini" in manager.providers:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "💡 *Want Gemini?* Use `/apikey` to add your Google API key."
                }
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
                    "options": model_options[:25],
                },
            }
        )
    elif selected_provider_id == "gemini" and not gemini_configured:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ Gemini requires an API key. Use `/apikey` to add one first.",
                },
            }
        )
    else:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚠️ No compatible models found for this provider.",
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
