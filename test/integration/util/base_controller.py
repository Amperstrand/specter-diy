"""
Abstract Controller base class

Defines the interface contract that all controllers must implement.
Controllers like SimController and HardwareController will inherit from this
to enable interchangeable usage in tests.
"""
from abc import ABC, abstractmethod


class BaseController(ABC):
    """
    Abstract base class for all controllers.

    Controllers handle interaction with hardware/simulator and must implement
    the following lifecycle and query methods:
    - start(): Initialize and launch the controller
    - load(): Prepare the controller for queries
    - shutdown(): Clean shutdown of the controller
    - query(): Send data and receive response
    """

    def __init__(self):
        """Initialize controller state."""
        pass

    @abstractmethod
    def start(self) -> None:
        """
        Start the controller.

        Must initialize all resources required for operation and
        launch any background processes.
        """
        pass

    @abstractmethod
    def load(self) -> None:
        """
        Load controller state and prepare for queries.

        This is called after start() and configures any necessary
        settings, connections, or state.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """
        Shutdown the controller cleanly.

        Must release all resources, close connections, and terminate
        any background processes.
        """
        pass

    @abstractmethod
    def query(self, data: str | bytes, commands: list[str | bytes] = []) -> str | bytes:
        """
        Send data to the controller and receive response.

        Args:
            data: Data to send to controller (str or bytes)
            commands: Optional list of commands to send after data
                     (for confirmations or additional actions)

        Returns:
            Response from controller (str or bytes)
        """
        pass
