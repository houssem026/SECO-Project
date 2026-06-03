"""Facade designer support scripts package."""

from __future__ import annotations

from typing import Any

__all__ = ["build_agent", "root_agent"]


def build_agent(*args: Any, **kwargs: Any) -> Any:
    from scripts.agent import build_agent as _build_agent

    return _build_agent(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "root_agent":
        from scripts.agent import root_agent

        return root_agent
    raise AttributeError(name)
