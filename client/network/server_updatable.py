from abc import ABC, abstractmethod

class ServerUpdatable(ABC):
    @abstractmethod
    def update_from_server(self, server_update: dict):
        pass
