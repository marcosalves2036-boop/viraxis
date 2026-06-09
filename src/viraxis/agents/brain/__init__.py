"""BRAIN agent package."""

# Lazy import: crewai is only loaded when run_brain is called.
# This avoids ImportError in contexts that do not use the agent (CLI, healthcheck).

__all__ = ["run_brain"]


def __getattr__(name: str):
    if name == "run_brain":
        from viraxis.agents.brain.runner import run_brain
        return run_brain
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
