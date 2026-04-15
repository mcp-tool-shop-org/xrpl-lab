"""Action registry — stable identity and dispatch for module actions."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from .modules import ModuleStep
from .state import LabState
from .transport.base import Transport

# Handler signature: all action handlers share this shape.
# Returns the updated context dict.
ActionHandler = Callable[
    [ModuleStep, LabState, Transport, str, dict, Console],
    Coroutine[Any, Any, dict],
]


@dataclass(frozen=True)
class ActionDef:
    """Metadata + handler for a registered action."""

    name: str
    handler: ActionHandler
    description: str = ""
    wallet_required: bool = False
    payload_fields: list[PayloadField] = field(default_factory=list)


# ── Payload schema (2B hook point — lightweight for now) ─────────────


@dataclass(frozen=True)
class PayloadField:
    """Schema for a single action argument."""

    name: str
    type: str = "str"  # str | int | decimal | bool | enum | list
    required: bool = False
    default: str | None = None
    choices: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class PayloadSchema:
    """Validation schema for an action's arguments."""

    fields: tuple[PayloadField, ...]

    def validate(self, args: dict[str, str]) -> dict[str, Any]:
        """Validate and coerce *args* against this schema.

        Returns a dict of coerced values.
        Raises ``PayloadError`` on the first invalid field.
        """
        from decimal import Decimal, InvalidOperation

        result: dict[str, Any] = {}
        known_names = {f.name for f in self.fields}

        # Reject unknown fields
        for key in args:
            if key not in known_names:
                raise PayloadError(
                    field=key,
                    message=f"Unknown field '{key}'",
                )

        for f in self.fields:
            raw = args.get(f.name)

            if raw is None:
                if f.required:
                    raise PayloadError(
                        field=f.name,
                        message=f"Missing required field '{f.name}'",
                    )
                if f.default is not None:
                    raw = f.default
                else:
                    continue

            # Type coercion
            try:
                if f.type == "str":
                    result[f.name] = raw
                elif f.type == "int":
                    result[f.name] = int(raw)
                elif f.type == "decimal":
                    result[f.name] = Decimal(raw)
                elif f.type == "bool":
                    result[f.name] = raw.lower() in ("true", "1", "yes")
                elif f.type == "enum":
                    if raw not in f.choices:
                        raise PayloadError(
                            field=f.name,
                            message=(
                                f"Invalid value '{raw}' for '{f.name}'; "
                                f"expected one of: {', '.join(f.choices)}"
                            ),
                        )
                    result[f.name] = raw
                elif f.type == "list":
                    result[f.name] = [v.strip() for v in raw.split(",")]
                else:
                    result[f.name] = raw
            except PayloadError:
                raise
            except (ValueError, TypeError, InvalidOperation) as exc:
                raise PayloadError(
                    field=f.name,
                    message=f"Invalid {f.type} for '{f.name}': {raw}",
                ) from exc

        return result


class PayloadError(Exception):
    """Raised when a payload field fails validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(message)


class UnknownActionError(Exception):
    """Raised when an action name is not in the registry."""

    def __init__(self, action: str):
        self.action = action
        super().__init__(f"Unknown action: '{action}'")


class DuplicateActionError(Exception):
    """Raised when trying to register an action that already exists."""

    def __init__(self, action: str):
        self.action = action
        super().__init__(f"Duplicate action registration: '{action}'")


# ── Global registry ──────────────────────────────────────────────────

_REGISTRY: dict[str, ActionDef] = {}


def register(action_def: ActionDef) -> None:
    """Register an action. Raises ``DuplicateActionError`` on collision."""
    if action_def.name in _REGISTRY:
        raise DuplicateActionError(action_def.name)
    _REGISTRY[action_def.name] = action_def


def resolve(name: str) -> ActionDef:
    """Look up an action by name. Raises ``UnknownActionError`` if missing."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownActionError(name) from None


def all_actions() -> dict[str, ActionDef]:
    """Return a read-only view of all registered actions."""
    return dict(_REGISTRY)


def is_registered(name: str) -> bool:
    """Check if an action name is registered."""
    return name in _REGISTRY


def clear() -> None:
    """Clear the registry. For testing only."""
    _REGISTRY.clear()
