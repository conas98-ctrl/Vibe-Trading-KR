"""Shared helpers for Korean broker connector bootstrap modules."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

PROFILE_ENVIRONMENTS = {
    "paper": "paper",
    "live-readonly": "live",
    "live": "live",
}


class KoreanConnectorConfigError(RuntimeError):
    """Raised when a Korean connector config is malformed."""


@dataclass(frozen=True)
class KoreanConnectorConfig:
    """Config shared by REST and local bridge Korean broker connectors."""

    connector: str
    profile: str = "paper"
    app_key: str = ""
    app_secret: str = ""
    access_token: str = ""
    account: str = ""
    account_product_code: str = ""
    base_url: str = ""
    paper_url: str = ""
    live_url: str = ""
    bridge_url: str = ""
    bridge_token: str = ""
    timeout: float = 15.0
    readonly: bool = True

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any] | None = None,
        *,
        connector: str,
        paper_url: str = "",
        live_url: str = "",
        bridge_url: str = "",
    ) -> "KoreanConnectorConfig":
        payload = dict(data or {})
        profile = str(payload.get("profile") or "paper").strip().lower()
        if profile not in PROFILE_ENVIRONMENTS:
            raise KoreanConnectorConfigError("profile must be 'paper', 'live-readonly' or 'live'")
        return cls(
            connector=connector,
            profile=profile,
            app_key=str(payload.get("app_key") or "").strip(),
            app_secret=str(payload.get("app_secret") or "").strip(),
            access_token=str(payload.get("access_token") or "").strip(),
            account=str(payload.get("account") or "").strip(),
            account_product_code=str(payload.get("account_product_code") or "").strip(),
            base_url=str(payload.get("base_url") or "").strip(),
            paper_url=str(payload.get("paper_url") or paper_url).strip(),
            live_url=str(payload.get("live_url") or live_url).strip(),
            bridge_url=str(payload.get("bridge_url") or bridge_url).strip(),
            bridge_token=str(payload.get("bridge_token") or "").strip(),
            timeout=float(payload.get("timeout") or 15.0),
            readonly=bool(payload.get("readonly", True)),
        )

    def with_overrides(self, **overrides: Any) -> "KoreanConnectorConfig":
        payload = asdict(self)
        for key, value in overrides.items():
            if key in payload and value not in (None, ""):
                payload[key] = value
        return type(self).from_mapping(
            payload,
            connector=self.connector,
            paper_url=self.paper_url,
            live_url=self.live_url,
            bridge_url=self.bridge_url,
        )

    @property
    def environment(self) -> str:
        return PROFILE_ENVIRONMENTS.get(self.profile, "paper")

    @property
    def endpoint(self) -> str:
        if self.base_url:
            return self.base_url
        if self.bridge_url:
            return self.bridge_url
        return self.paper_url if self.environment == "paper" else self.live_url


OVERRIDE_KEYS = (
    "app_key",
    "app_secret",
    "access_token",
    "account",
    "account_product_code",
    "base_url",
    "bridge_url",
    "bridge_token",
    "profile",
)


def build_config(
    *,
    config_path: Path,
    connector: str,
    profile_config: Mapping[str, Any] | None,
    overrides: Mapping[str, Any] | None,
    paper_url: str = "",
    live_url: str = "",
    bridge_url: str = "",
) -> KoreanConnectorConfig:
    base = asdict(load_config(config_path, connector=connector, paper_url=paper_url, live_url=live_url, bridge_url=bridge_url))
    for key, value in dict(profile_config or {}).items():
        if value is not None:
            base[key] = value
    cfg = KoreanConnectorConfig.from_mapping(base, connector=connector, paper_url=paper_url, live_url=live_url, bridge_url=bridge_url)
    clean = {k: v for k, v in dict(overrides or {}).items() if k in OVERRIDE_KEYS and v not in (None, "")}
    return cfg.with_overrides(**clean) if clean else cfg


def load_config(
    path: Path,
    *,
    connector: str,
    paper_url: str = "",
    live_url: str = "",
    bridge_url: str = "",
) -> KoreanConnectorConfig:
    if not path.exists():
        return KoreanConnectorConfig.from_mapping({}, connector=connector, paper_url=paper_url, live_url=live_url, bridge_url=bridge_url)
    try:
        return KoreanConnectorConfig.from_mapping(
            json.loads(path.read_text(encoding="utf-8")),
            connector=connector,
            paper_url=paper_url,
            live_url=live_url,
            bridge_url=bridge_url,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise KoreanConnectorConfigError(f"invalid {connector} config at {path}: {exc}") from exc


def save_config(path: Path, config: KoreanConnectorConfig) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def check_status(config: KoreanConnectorConfig, *, label: str, bridge: bool = False) -> dict[str, Any]:
    missing = _missing_fields(config, bridge=bridge)
    report = {
        "status": "ok" if not missing else "error",
        "config": public_config(config),
        "endpoint": config.endpoint,
        "paper_guard": "profile_endpoint_separated" if not bridge else "local_bridge_endpoint",
    }
    if missing:
        report["error"] = f"{label} connector not configured: missing {', '.join(missing)}."
    return report


def unsupported_or_unconfigured(config: KoreanConnectorConfig, *, label: str, operation: str, bridge: bool = False) -> dict[str, Any]:
    missing = _missing_fields(config, bridge=bridge)
    if missing:
        return {
            "status": "error",
            "profile": config.profile,
            "error": f"{label} connector not configured: missing {', '.join(missing)}.",
        }
    return {
        "status": "error",
        "profile": config.profile,
        "error": f"{operation} is not implemented for {label} yet; use the broker API catalog for endpoint-level coverage.",
    }


def public_config(config: KoreanConnectorConfig) -> dict[str, Any]:
    data = asdict(config)
    for key in ("app_secret", "access_token", "bridge_token"):
        if data.get(key):
            data[key] = "***redacted***"
    if data.get("app_key"):
        data["app_key"] = data["app_key"][:4] + "***"
    return data


def _missing_fields(config: KoreanConnectorConfig, *, bridge: bool) -> list[str]:
    if bridge:
        missing = []
        if not config.bridge_url:
            missing.append("bridge_url")
        if not config.bridge_token:
            missing.append("bridge_token")
        return missing
    return [name for name in ("app_key", "app_secret") if not getattr(config, name)]
