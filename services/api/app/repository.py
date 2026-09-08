from typing import Protocol

class Repository(Protocol):
    datasets: dict[str, dict]
    analyses: dict[str, dict]

class InMemoryRepository:
    def __init__(self):
        self.datasets: dict[str, dict] = {}
        self.analyses: dict[str, dict] = {}

repository = InMemoryRepository()
