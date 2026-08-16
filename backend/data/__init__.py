from backend.data.cache import DataCache
from backend.data.qmt_client import QMTClient

qmt_client = QMTClient()
data_cache = DataCache()

__all__ = ["DataCache", "QMTClient", "data_cache", "qmt_client"]
