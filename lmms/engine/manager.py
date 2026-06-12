from typing import Optional
from lmms.engine.runtimes.llama_cpp import LlamaCppRuntime
from lmms.engine.cache_manager import CacheManager
from lmms.engine.air import AirScheduler, RamCache, AirSwapper

class EngineManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EngineManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
        
    def __init__(self):
        if not self._initialized:
            self.runtime = LlamaCppRuntime()
            self.cache = CacheManager()
            self.air_scheduler = AirScheduler()
            self.air_ram_cache = RamCache()
            self.air_swapper = AirSwapper(self.air_scheduler, self.air_ram_cache)
            self._initialized = True

engine_manager = EngineManager()
