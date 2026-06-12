import os
from typing import Dict, Any, Optional
from lmms.engine.runtimes.base import RuntimeContract

try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

class LlamaCppRuntime(RuntimeContract):
    def __init__(self):
        self._model: Optional[Llama] = None
        self._model_path: Optional[str] = None
        self._is_loaded = False

    def load_model(self, model_id: str) -> bool:
        if Llama is None:
            print("ERROR: llama-cpp-python not installed.")
            return False
            
        # Hardcoding the models directory for now
        models_dir = os.path.expanduser("~/.lmms/models")
        # In reality, model_id is mapped to a file path. Let's assume model_id is the filename if it ends with .gguf
        if model_id.endswith(".gguf"):
            file_name = model_id
        else:
            # Let's map qwen3:8b to our downloaded model for testing
            file_name = "qwen1_5-0_5b-chat-q4_k_m.gguf"
            
        full_path = os.path.join(models_dir, file_name)
        
        if not os.path.exists(full_path):
            print(f"ERROR: Model file not found at {full_path}")
            return False
            
        try:
            self._model = Llama(
                model_path=full_path,
                n_gpu_layers=-1, # All layers to GPU
                n_ctx=2048,
                verbose=False
            )
            self._model_path = full_path
            self._is_loaded = True
            return True
        except Exception as e:
            print(f"Failed to load model: {e}")
            return False

    def unload_model(self) -> bool:
        if self._model:
            del self._model
            self._model = None
            self._is_loaded = False
        return True

    def chat(self, model: str, messages: list, stream: bool = False, options: dict = None, **kwargs) -> Any:
        context = {'messages': messages}
        return self.generate(context, stream)

    def generate(self, context: Any, stream: bool = False) -> Any:
        if not self._is_loaded or not self._model:
            raise RuntimeError("No model is currently loaded in LlamaCppRuntime.")
            
        # Extract messages from context
        # Standardize expected context: {"messages": [...]}
        messages = list(context.get("messages", []))
        mode = context.get("mode", "deep")
        think = context.get("think", True)
        
        # Inject system prompt if not present
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            sys_msg = "You are a helpful AI assistant."
            if mode == "code":
                sys_msg = "You are an expert programmer. Write clean, efficient, and well-documented code. Do not use conversational filler."
            elif mode == "research":
                sys_msg = "You are an expert researcher. Provide highly detailed, accurate, and analytical answers with logical structuring."
            elif mode == "fast":
                sys_msg = "You are a fast and concise assistant. Answer directly without thinking or explanation."
            
            if think is False and mode not in ["fast"]:
                sys_msg += " Do not output any thought process or <think> tags. Answer directly."
                
            messages.insert(0, {"role": "system", "content": sys_msg})

        
        if stream:
            # Create a generator that yields text chunks
            response_generator = self._model.create_chat_completion(
                messages=messages,
                stream=True,
                max_tokens=1024
            )
            
            def stream_response():
                for chunk in response_generator:
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            yield {"message": {"content": delta["content"]}}
            return stream_response()
        else:
            response = self._model.create_chat_completion(
                messages=messages,
                stream=False,
                max_tokens=1024
            )
            return {"message": {"content": response["choices"][0]["message"]["content"]}}

    def embed(self, text: str) -> list[float]:
        # Dummy for now
        return [0.0]

    def tokenize(self, text: str) -> list[int]:
        if self._is_loaded and self._model:
            return self._model.tokenize(text.encode("utf-8"))
        return []

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok" if Llama else "missing_dependency",
            "backend": "llama.cpp",
            "model_loaded": self._is_loaded,
            "model_path": self._model_path
        }
