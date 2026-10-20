"""xAI adapter.

Uses XAI_API_KEY and POST https://api.x.ai/v1/chat/completions with model
grok-4.7. The demo leaves MODEL_PROVIDER=mock, so this module is not called.
"""

from identityguard.models.hosted import XAIAdapter

__all__ = ["XAIAdapter"]
