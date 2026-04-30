"""
============================================================
circuit_breaker.py — Provider Health Tracking + Auto-Failover
============================================================
Tracks per-provider failure rates. Automatically:
  - Switches to fallback provider when PRIMARY fails too often
  - Recovers PRIMARY after cooldown period (30s)
  - Logs all state transitions

States:
  CLOSED    → normal operation, calls go to PRIMARY
  OPEN      → PRIMARY is dead, calls go to FALLBACK immediately
  HALF_OPEN → testing PRIMARY, if it works → CLOSED, else → OPEN

Persisted to data/state.db so survives restarts.
"""
import time
from dataclasses import dataclass, field
from backend.persistent_state import set_state, get_state


@dataclass
class ProviderCircuit:
    name: str
    error_threshold: int = 3          # failures before opening
    cooldown_seconds: int = 30        # wait before testing PRIMARY
    error_window_seconds: int = 60    # time window for counting errors
    _errors: list[float] = field(default_factory=list)
    _opened_at: float = 0
    _state: str = "CLOSED"            # CLOSED | OPEN | HALF_OPEN

    def record_error(self):
        now = time.time()
        self._errors = [e for e in self._errors if now - e < self.error_window_seconds]
        self._errors.append(now)
        if len(self._errors) >= self.error_threshold and self._state == "CLOSED":
            self._state = "OPEN"
            self._opened_at = now
            print(f"[Circuit] 🔴 {self.name} OPEN — {len(self._errors)} errors in {self.error_window_seconds}s. Switching to fallback.")

    def record_success(self):
        self._errors = []
        if self._state == "HALF_OPEN":
            self._state = "CLOSED"
            print(f"[Circuit] 🟢 {self.name} CLOSED — recovered successfully.")
        elif self._state == "OPEN":
            elapsed = time.time() - self._opened_at
            if elapsed > self.cooldown_seconds:
                self._state = "HALF_OPEN"
                print(f"[Circuit] 🟡 {self.name} HALF_OPEN — testing PRIMARY...")

    def can_try(self) -> bool:
        """Should we try the PRIMARY provider now?"""
        if self._state == "CLOSED":
            return True
        if self._state == "OPEN":
            if time.time() - self._opened_at > self.cooldown_seconds:
                self._state = "HALF_OPEN"
                print(f"[Circuit] 🟡 {self.name} HALF_OPEN — testing PRIMARY...")
                return True
            return False
        if self._state == "HALF_OPEN":
            return True
        return True

    @property
    def is_open(self) -> bool:
        return self._state == "OPEN"

    def to_dict(self) -> dict:
        return {"state": self._state, "opened_at": self._opened_at, "error_count": len(self._errors)}


# ── Global provider circuits ─────────────────────────────────
_circuits: dict[str, ProviderCircuit] = {}


def get_circuit(name: str) -> ProviderCircuit:
    """Get or create a circuit breaker for a provider."""
    if name not in _circuits:
        circuit = ProviderCircuit(name=name)
        # Restore from persistent state if available
        saved = get_state("circuits", name)
        if saved:
            circuit._state = saved.get("state", "CLOSED")
            circuit._opened_at = saved.get("opened_at", 0)
        _circuits[name] = circuit
    return _circuits[name]


def save_circuit_state(name: str):
    """Persist circuit state to SQLite."""
    circuit = get_circuit(name)
    set_state("circuits", name, circuit.to_dict())


def check_circuit(provider: str) -> bool:
    """
    Check if we should try the given provider.
    Returns True if provider is healthy (not open).
    """
    circuit = get_circuit(provider)
    return circuit.can_try()


def record_error(provider: str):
    """Record a failure for the provider."""
    circuit = get_circuit(provider)
    circuit.record_error()
    save_circuit_state(provider)


def record_success(provider: str):
    """Record a success for the provider."""
    circuit = get_circuit(provider)
    circuit.record_success()
    save_circuit_state(provider)


async def call_with_circuit_breaker(
    provider_name: str,
    fallback_name: str,
    primary_func,
    fallback_func,
    *args,
    **kwargs
) -> str:
    """
    Call primary_func with circuit breaker protection.
    If PRIMARY circuit is open, skip directly to fallback_func.
    If PRIMARY succeeds, close circuit.
    If PRIMARY fails, open circuit and try fallback.
    """
    import asyncio
    circuit = get_circuit(provider_name)

    # Try PRIMARY
    if circuit.can_try():
        try:
            result = primary_func(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            if result:
                record_success(provider_name)
                return result
            else:
                record_error(provider_name)
        except Exception as e:
            print(f"[Circuit] {provider_name} exception: {type(e).__name__}: {e}")
            record_error(provider_name)
    else:
        print(f"[Circuit] {provider_name} circuit OPEN — skipping PRIMARY")

    # Try FALLBACK
    try:
        result = fallback_func(*args, **kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return result or ""
    except Exception as e:
        print(f"[Circuit] {fallback_name} fallback also failed: {type(e).__name__}")
        return ""


def get_all_circuit_status() -> dict:
    """Return health status of all providers."""
    return {name: c.to_dict() for name, c in _circuits.items()}
