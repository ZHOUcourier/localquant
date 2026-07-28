from backend.data.qmt_client import QMTClient
from backend.data.cache import DataCache

qmt_client = QMTClient()
data_cache = DataCache()

__all__ = ["qmt_client", "data_cache", "QMTClient", "DataCache"]
