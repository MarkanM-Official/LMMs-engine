import time
import threading
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from lmms.engine.air.loader import AirLoader, ModelProfile
from lmms.engine.air.pager import AirPager

@dataclass
class AirGroup:
    group_id: int
    models: Dict[str, str] # role -> model_name (e.g. text -> qwen3:8b)
    active_role: Optional[str] = None

class AirScheduler:
    def __init__(self):
        self.loader = AirLoader()
        self.pager = AirPager()
        self.groups: Dict[int, AirGroup] = {}
        self.swap_count = 0
        self.total_swap_time_ms = 0.0
        self._global_lock = threading.Lock()

    def parse_input_and_create_group(self, group_id: int, config_string: str):
        """
        Parses config like 'text:qwen image:llava video:qwen2vl'
        """
        if len(self.groups) >= 4:
            raise ValueError("Maximum 4 groups per AIR session allowed.")
            
        models = {}
        parts = config_string.split()
        
        if len(parts) > 6:
            raise ValueError("Maximum 6 models per group allowed.")
        if len(parts) < 1:
            raise ValueError("Minimum 1 model per group required.")
            
        for part in parts:
            if ":" in part:
                role, name = part.split(":", 1)
                models[role] = name
            else:
                # Default to text if no role specified
                models["text"] = part
                
        self.groups[group_id] = AirGroup(group_id=group_id, models=models)

    def route_request(self, group_id: int, target_role: str, messages: list):
        """
        Routes the inference request to the correct model in the paired group.
        If the model is not currently in VRAM, it swaps it in safely.
        """
        # Global hardware lock ensures single-slot execution across all groups
        with self._global_lock:
            if group_id not in self.groups:
                raise ValueError(f"Group {group_id} not found.")
                
            group = self.groups[group_id]
            if target_role not in group.models:
                raise ValueError(f"Role {target_role} not found in group {group_id}.")
                
            target_model_name = group.models[target_role]
            
            # Check if we need to swap
            is_already_active = (self.pager.active_profile and 
                               self.pager.active_profile.model_name == target_model_name)
                               
            if not is_already_active:
                print(f"--- AIR SCHEDULER: Swapping to {target_model_name} (Role: {target_role}) ---")
                t0 = time.time()
                
                profile = self.loader.analyze_model(target_model_name)
                if not profile:
                    raise RuntimeError(f"Could not analyze model {target_model_name}. Check if .gguf exists.")
                    
                success = self.pager.load(profile)
                if not success:
                    raise RuntimeError(f"Failed to page in {target_model_name}")
                    
                swap_time = (time.time() - t0) * 1000
                self.swap_count += 1
                self.total_swap_time_ms += swap_time
                print(f"--- AIR SCHEDULER: Warm start complete in {swap_time:.2f}ms ---")
                
            group.active_role = target_role
            
            # Execute stream and yield within the lock to prevent concurrent swaps
            generator = self.pager.execute_stream(messages)
            for chunk in generator:
                yield chunk

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "swap_count": self.swap_count,
            "effective_warm_start_latency_ms": round(self.total_swap_time_ms / max(1, self.swap_count), 2),
            "active_groups": len(self.groups),
            "current_active_model": self.pager.active_profile.model_name if self.pager.active_profile else None
        }
