"""The one model gateway (SR-09, SR-06, SR-10, ARCHITECTURE 9).

Every model-bound path goes through this gateway. It runs the carrier normalize
first, so a smuggled payload does not reach the model, and it fails closed on an
error. The harness may bypass the sanitize in an isolated sandbox only, never to an
API, and every such call is recorded (SR-10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class GatewayCall:
    sanitized: bool
    sandbox: bool
    ok: bool
    note: str


@dataclass
class ModelGateway:
    """Wrap a model callable(text)->text with the sanitize-before-call rule."""

    model: Callable[[str], str]
    is_api: bool = False
    audit_log: list[GatewayCall] = field(default_factory=list)

    def call(self, text: str, sandbox: bool = False) -> str:
        if sandbox:
            # SR-10: a raw sample is allowed only in a sandbox, never to an API.
            if self.is_api:
                self.audit_log.append(GatewayCall(False, True, False, "sandbox to API refused"))
                raise RuntimeError("the gateway refuses a raw sandbox sample to an API (SR-10)")
            self.audit_log.append(GatewayCall(False, True, True, "sandbox raw sample"))
            return self._invoke(text)

        # normal path: sanitize carriers before the model sees the text (SR-06)
        from ..bleach.normalize import normalize_carriers

        clean = normalize_carriers(text)
        try:
            out = self._invoke(clean)
        except Exception as exc:  # fail closed
            self.audit_log.append(GatewayCall(True, False, False, f"model error: {exc}"))
            raise RuntimeError(f"the model call failed and the gateway failed closed: {exc}")
        self.audit_log.append(GatewayCall(True, False, True, "sanitized model call"))
        return out

    def _invoke(self, text: str) -> str:
        return self.model(text)
