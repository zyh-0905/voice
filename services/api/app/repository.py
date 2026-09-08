from typing import Protocol
import os

class Repository(Protocol):
    datasets: dict
    analyses: dict
class InMemoryRepository:
    def __init__(self): self.datasets = {}; self.analyses = {}
repository = InMemoryRepository()

def get_repository():
    if os.getenv('USE_DATABASE','').lower() in ('1','true','yes'):
        from .sql_repository import SQLAlchemyRepository
        return SQLAlchemyRepository()
    return InMemoryRepository()
