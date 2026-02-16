#!/usr/bin/env python3
"""
Slack App Manifest Manager - Manage Slack apps as infrastructure-as-code.

Creates, updates, exports, and diffs Slack app configurations using
the App Manifest API. All tokens stored in Vaultwarden.

Usage:
    python -m tools.slack_app_manager export --app-id A12345 --out manifests/brain-assistant.json
    python -m tools.slack_app_manager create --manifest manifests/slack-user-client.json
    python -m tools.slack_app_manager update --app-id A12345 --manifest manifests/brain-assistant.json
    python -m tools.slack_app_manager diff --app-id A12345 --manifest manifests/brain-assistant.json
    python -m tools.slack_app_manager validate --manifest manifests/brain-assistant.json
    python -m tools.slack_app_manager rotate-token
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import requests


class SlackManifestError(Exception):
    """Base error for manifest operations."""
    pass


class TokenExpiredError(SlackManifestError):
    """Config token expired and refresh failed."""
    pass


class SlackManifestClient:
    """Client for Slack App Manifest API.

    Uses configuration tokens (access + refresh) stored in Vaultwarden.
    Automatically rotates the access token when expired.
    """

    API_BASE = "https://slack.com/api"

    def __init__(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
    ):
        if access_token is None or refresh_token is None:
            access_token, refresh_token = self._load_tokens()

        self.access_token = access_token
        self.refresh_token = refresh_token

    @staticmethod
    def _load_tokens() -> Tuple[str, str]:
        """Load config tokens from Vaultwarden."""
        from clients.vaultwarden_client import get_client
        client = get_client()
        access = client.get_secret("SLACK_CONFIG_ACCESS_TOKEN")
        refresh = client.get_secret("SLACK_CONFIG_REFRESH_TOKEN")
        return access, refresh

    def _save_tokens(self, access_token: str, refresh_token: str):
        """Save rotated tokens back to Vaultwarden."""
        from clients.vaultwarden_client import get_client
        client = get_client()
        # Delete old entries first, then create new ones
        # set_secret creates new ciphers, so we need to handle duplicates
        client.set_secret(
            "SLACK_CONFIG_ACCESS_TOKEN", access_token,
            "Slack Configuration Access Token (12hr, auto-rotated)"
        )
        client.set_secret(
            "SLACK_CONFIG_REFRESH_TOKEN", refresh_token,
            "Slack Configuration Refresh Token (auto-rotated)"
        )

    def _api_call(self, method: str, **kwargs) -> Dict[str, Any]:
        """Make an authenticated API call to Slack."""
        url = f"{self.API_BASE}/{method}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = requests.post(url, headers=headers, json=kwargs)
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "unknown_error")
            # Try token rotation on auth errors
            if error in ("token_expired", "invalid_auth", "not_authed"):
                self.rotate_token()
                headers["Authorization"] = f"Bearer {self.access_token}"
                response = requests.post(url, headers=headers, json=kwargs)
                response.raise_for_status()
                data = response.json()
                if not data.get("ok"):
                    raise SlackManifestError(
                        f"API error after token rotation: {data.get('error')}"
                    )
            else:
                errors = data.get("errors", [])
                if errors:
                    detail = "; ".join(
                        f"{e.get('message', '')} (at {e.get('pointer', '?')})"
                        for e in errors
                    )
                    raise SlackManifestError(f"{error}: {detail}")
                raise SlackManifestError(f"API error: {error}")

        return data

    def rotate_token(self) -> Tuple[str, str]:
        """Rotate the configuration access token using the refresh token.

        Returns:
            Tuple of (new_access_token, new_refresh_token).
        """
        url = f"{self.API_BASE}/tooling.tokens.rotate"
        response = requests.post(url, data={
            "refresh_token": self.refresh_token,
        })
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            raise TokenExpiredError(
                f"Token rotation failed: {data.get('error')}. "
                "Generate new tokens at https://api.slack.com/apps"
            )

        self.access_token = data["token"]
        self.refresh_token = data["refresh_token"]

        # Persist to Vaultwarden
        self._save_tokens(self.access_token, self.refresh_token)

        print(f"Token rotated. Expires: {data.get('exp', 'unknown')}")
        return self.access_token, self.refresh_token

    def export_manifest(self, app_id: str) -> Dict[str, Any]:
        """Export an existing app's manifest."""
        data = self._api_call("apps.manifest.export", app_id=app_id)
        return data.get("manifest", {})

    def create_app(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new app from a manifest.

        Returns:
            Dict with app_id, credentials, and oauth info.
        """
        data = self._api_call("apps.manifest.create", manifest=manifest)
        return {
            "app_id": data.get("app_id"),
            "credentials": data.get("credentials", {}),
            "oauth_authorize_url": data.get("oauth_authorize_url"),
        }

    def update_app(self, app_id: str, manifest: Dict[str, Any]) -> bool:
        """Update an existing app's manifest.

        Returns:
            True if successful.
        """
        self._api_call("apps.manifest.update", app_id=app_id, manifest=manifest)
        return True

    def validate_manifest(self, manifest: Dict[str, Any], app_id: Optional[str] = None) -> bool:
        """Validate a manifest against the Slack schema.

        Returns:
            True if valid.

        Raises:
            SlackManifestError: If validation fails with details.
        """
        kwargs: Dict[str, Any] = {"manifest": manifest}
        if app_id:
            kwargs["app_id"] = app_id
        self._api_call("apps.manifest.validate", **kwargs)
        return True

    def delete_app(self, app_id: str) -> bool:
        """Delete an app."""
        self._api_call("apps.manifest.delete", app_id=app_id)
        return True


def _deep_diff(a: Any, b: Any, path: str = "") -> list:
    """Compute differences between two dicts/lists recursively."""
    diffs = []
    if isinstance(a, dict) and isinstance(b, dict):
        all_keys = set(list(a.keys()) + list(b.keys()))
        for key in sorted(all_keys):
            p = f"{path}.{key}" if path else key
            if key not in a:
                diffs.append(f"  + {p}: {json.dumps(b[key])}")
            elif key not in b:
                diffs.append(f"  - {p}: {json.dumps(a[key])}")
            else:
                diffs.extend(_deep_diff(a[key], b[key], p))
    elif isinstance(a, list) and isinstance(b, list):
        for i in range(max(len(a), len(b))):
            p = f"{path}[{i}]"
            if i >= len(a):
                diffs.append(f"  + {p}: {json.dumps(b[i])}")
            elif i >= len(b):
                diffs.append(f"  - {p}: {json.dumps(a[i])}")
            else:
                diffs.extend(_deep_diff(a[i], b[i], p))
    elif a != b:
        diffs.append(f"  ~ {path}: {json.dumps(a)} -> {json.dumps(b)}")
    return diffs


def cmd_export(args):
    """Export an app's manifest to a JSON file."""
    client = SlackManifestClient()
    manifest = client.export_manifest(args.app_id)

    output = json.dumps(manifest, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(output + "\n")
        print(f"Manifest exported to {args.out}")
    else:
        print(output)
    return 0


def cmd_create(args):
    """Create a new app from a manifest file."""
    manifest = json.loads(Path(args.manifest).read_text())
    client = SlackManifestClient()
    result = client.create_app(manifest)

    print(f"App created: {result['app_id']}")
    if result.get("oauth_authorize_url"):
        print(f"Authorize at: {result['oauth_authorize_url']}")
    if result.get("credentials"):
        print(f"Client ID: {result['credentials'].get('client_id')}")
        print(f"Client Secret: {result['credentials'].get('client_secret')}")
    return 0


def cmd_update(args):
    """Update an existing app from a manifest file."""
    manifest = json.loads(Path(args.manifest).read_text())
    client = SlackManifestClient()
    client.update_app(args.app_id, manifest)
    print(f"App {args.app_id} updated successfully")
    return 0


def cmd_validate(args):
    """Validate a manifest file."""
    manifest = json.loads(Path(args.manifest).read_text())
    client = SlackManifestClient()
    client.validate_manifest(manifest, app_id=args.app_id)
    print("Manifest is valid")
    return 0


def cmd_diff(args):
    """Show differences between live app and manifest file."""
    manifest_local = json.loads(Path(args.manifest).read_text())
    client = SlackManifestClient()
    manifest_live = client.export_manifest(args.app_id)

    diffs = _deep_diff(manifest_live, manifest_local)
    if not diffs:
        print("No differences (live app matches manifest)")
    else:
        print(f"Differences ({len(diffs)} changes):")
        print("  Legend: + added, - removed, ~ changed")
        print()
        for d in diffs:
            print(d)
    return 0


def cmd_rotate(args):
    """Rotate the configuration access token."""
    client = SlackManifestClient()
    client.rotate_token()
    print("Token rotated and saved to Vaultwarden")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="slack-app-manager",
        description="Manage Slack apps via manifests (infrastructure-as-code).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # export
    p = subparsers.add_parser("export", help="Export app manifest to JSON.")
    p.add_argument("--app-id", required=True, help="Slack app ID (A...).")
    p.add_argument("--out", help="Output file path (prints to stdout if omitted).")

    # create
    p = subparsers.add_parser("create", help="Create app from manifest.")
    p.add_argument("--manifest", required=True, help="Path to manifest JSON file.")

    # update
    p = subparsers.add_parser("update", help="Update app from manifest.")
    p.add_argument("--app-id", required=True, help="Slack app ID.")
    p.add_argument("--manifest", required=True, help="Path to manifest JSON file.")

    # validate
    p = subparsers.add_parser("validate", help="Validate a manifest file.")
    p.add_argument("--manifest", required=True, help="Path to manifest JSON file.")
    p.add_argument("--app-id", help="Optional app ID for context-specific validation.")

    # diff
    p = subparsers.add_parser("diff", help="Diff live app vs manifest file.")
    p.add_argument("--app-id", required=True, help="Slack app ID.")
    p.add_argument("--manifest", required=True, help="Path to manifest JSON file.")

    # rotate-token
    subparsers.add_parser("rotate-token", help="Rotate configuration access token.")

    args = parser.parse_args()
    commands = {
        "export": cmd_export,
        "create": cmd_create,
        "update": cmd_update,
        "validate": cmd_validate,
        "diff": cmd_diff,
        "rotate-token": cmd_rotate,
    }

    try:
        return commands[args.command](args)
    except SlackManifestError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(f"File not found: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
