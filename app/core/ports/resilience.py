from abc import ABC, abstractmethod


class ResiliencePort(ABC):
    """
    Interface for distributed resilience patterns (Circuit Breaker).
    """

    @abstractmethod
    async def is_circuit_open(self, service_name: str) -> bool:
        """Checks if the circuit for a service is open."""
        pass

    @abstractmethod
    async def record_failure(self, service_name: str, threshold: int = 5, window: int = 60) -> bool:
        """Records a failure. Returns True if circuit should open."""
        pass

    @abstractmethod
    async def record_success(self, service_name: str) -> None:
        """Resets failure count for a service."""
        pass

    @abstractmethod
    async def allow_probe(self, service_name: str) -> bool:
        """Determines if a single request should be allowed when the circuit is open (Half-Open state)."""
        pass
