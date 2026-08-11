"""Provider registry and task-class model routing.

Adding a provider is one file plus one ``register()`` call. That is the contribution
path we most want to be obvious, so nothing else in the codebase is allowed to know
which providers exist.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from noema.core.errors import FeatureUnavailable, NoemaError
from noema.providers.base import AIProvider, Capabilities, TaskClass

ProviderFactory = Callable[..., AIProvider]

_REGISTRY: dict[str, ProviderFactory] = {}

#: Providers that never leave the machine. In local mode the registry is restricted
#: to these, so the guarantee is enforced by code rather than by documentation.
LOCAL_PROVIDERS = frozenset({"ollama", "mock", "local-embeddings"})


class UnknownProvider(NoemaError):
    slug = "unknown-provider"
    title = "Unknown AI provider"


def register(name: str) -> Callable[[ProviderFactory], ProviderFactory]:
    def decorator(factory: ProviderFactory) -> ProviderFactory:
        _REGISTRY[name] = factory
        return factory

    return decorator


def available(local_mode: bool = False) -> list[str]:
    names = sorted(_REGISTRY)
    return [n for n in names if n in LOCAL_PROVIDERS] if local_mode else names


def create(name: str, *, local_mode: bool = False, **kwargs: object) -> AIProvider:
    if name not in _REGISTRY:
        raise UnknownProvider(
            f"Unknown provider {name!r}. Available: {', '.join(available(local_mode))}"
        )
    if local_mode and name not in LOCAL_PROVIDERS:
        raise FeatureUnavailable(
            f"Provider {name!r} requires network access, which is disabled in local mode."
        )
    return _REGISTRY[name](**kwargs)


@dataclass(frozen=True, slots=True)
class Route:
    """Which provider and model handle a given task class."""

    provider: str
    model: str | None = None


class Router:
    """Resolves a task to a provider, most specific configuration winning.

    Order: notebook override → user setting → deployment default.
    """

    def __init__(
        self,
        default_provider: str,
        task_models: dict[TaskClass, str] | None = None,
        embedding_provider: str | None = None,
    ) -> None:
        self.default_provider = default_provider
        self.task_models = task_models or {}
        self.embedding_provider = embedding_provider or default_provider

    def resolve(
        self,
        task: TaskClass,
        *,
        notebook_override: str | None = None,
        user_preference: str | None = None,
    ) -> Route:
        if task is TaskClass.EMBED:
            return Route(self.embedding_provider, self.task_models.get(task))
        provider = notebook_override or user_preference or self.default_provider
        return Route(provider, self.task_models.get(task) or None)


def supports_structured(capabilities: Capabilities) -> bool:
    return capabilities.structured_output != "none"
