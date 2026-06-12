from typing import List, Dict, Any, Optional

class ModelManifest:
    """Standardized model format across LMMs."""
    
    def __init__(self, 
                 model_id: str, 
                 provider: str, 
                 path: str, 
                 format: str, 
                 capabilities: List[str] = None,
                 context: int = 8192,
                 quantization: str = "Unknown",
                 size: int = 0,
                 source: str = "Unknown"):
        self.id = model_id
        self.provider = provider
        self.path = path
        self.format = format
        self.capabilities = capabilities or ["text"]
        self.context = context
        self.quantization = quantization
        self.size = size
        self.source = source
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "path": self.path,
            "format": self.format,
            "capabilities": self.capabilities,
            "context": self.context,
            "quantization": self.quantization,
            "size": self.size,
            "source": self.source
        }
