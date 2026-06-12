import os
import json
import threading
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uvicorn
from huggingface_hub import hf_hub_download

from lmms.engine.manager import engine_manager

app = FastAPI(title="LMMs Engine API")

# Ensure models directory exists
MODELS_DIR = os.path.expanduser("~/.lmms/models")
os.makedirs(MODELS_DIR, exist_ok=True)

class LoadRequest(BaseModel):
    model_name: str
    model_path: Optional[str] = None

class UnloadRequest(BaseModel):
    model_name: str

class PullRequest(BaseModel):
    model_name: str

class ChatRequest(BaseModel):
    model_name: str
    messages: List[Dict[str, str]]
    stream: bool = True
    mode: Optional[str] = "deep"
    think: Optional[bool] = True

class DoctorRequest(BaseModel):
    fix: bool = False



@app.post("/v1/models/load")
async def load_model(req: LoadRequest):
    path = req.model_path or os.path.join(MODELS_DIR, f"{req.model_name}.gguf")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Model file not found")
        
    size_gb = os.path.getsize(path) / (1024**3)
    
    if not engine_manager.cache.can_fit(size_gb):
        raise HTTPException(status_code=507, detail="Insufficient VRAM/RAM to load model")
        
    # Register in cache
    engine_manager.cache.load_model(req.model_name, size_gb)
    
    # Actually load into runtime (llama_cpp)
    success = engine_manager.runtime.load_model(path)
    if not success:
        engine_manager.cache.unload_model(req.model_name)
        raise HTTPException(status_code=500, detail="Failed to initialize runtime")
        
    return {"status": "success", "stats": engine_manager.cache.get_stats()}

@app.post("/v1/models/unload")
def unload_model(req: UnloadRequest):
    engine_manager.runtime.unload_model()
    engine_manager.cache.unload_model(req.model_name)
    engine_manager.air_scheduler.remove_model(req.model_name)
    return {"status": "success", "message": f"Model {req.model_name} unloaded."}

@app.get("/v1/air/ps")
def air_ps():
    return engine_manager.air_scheduler.get_ps()

@app.get("/v1/air/stats")
def air_stats():
    from lmms.engine.air.stats import AirStats
    return AirStats.get_system_stats()

@app.get("/v1/air/cache")
def air_cache():
    import os
    from lmms.engine.registry import RegistryManager
    reg = RegistryManager()
    
    # Get all downloaded models
    disk_models = []
    if os.path.exists(reg.models_dir):
        for f in os.listdir(reg.models_dir):
            if f.endswith(".gguf"):
                disk_models.append(f.replace(".gguf", ""))
                
    vram_models = [m["model"] for m in engine_manager.air_scheduler.get_ps() if m["vram_gb"] > 0]
    ram_models = engine_manager.air_ram_cache.get_models()
    
    return {
        "vram_models": vram_models,
        "ram_models": ram_models,
        "disk_models": [m for m in disk_models if m not in vram_models and m not in ram_models]
    }

@app.post("/v1/air/generate")
def air_generate(req: ChatRequest):
    model_name = req.model_name
    
    # We don't forcefully evict everything anymore.
    # The Swapper will automatically handle eviction if VRAM is constrained.
    
    # We must resolve the path to load the model physically
    import os, json
    from lmms.engine.registry import RegistryManager
    reg = RegistryManager()
    path = os.path.join(reg.models_dir, f"{model_name}.gguf")
    
    if not os.path.exists(path):
        # Try to resolve via downloads.json mapping
        try:
            downloads_file = os.path.expanduser("~/.lmms/logs/downloads.json")
            if os.path.exists(downloads_file):
                with open(downloads_file, "r") as f: d = json.load(f)
                if model_name in d and d[model_name].get("file"):
                    path = os.path.join(reg.models_dir, d[model_name]["file"])
        except Exception: pass

    if not os.path.exists(path):
        # Fallback to fuzzy search
        search_term = model_name.replace(":", "-").lower()
        for f in os.listdir(reg.models_dir):
            if f.endswith(".gguf") and search_term in f.lower():
                path = os.path.join(reg.models_dir, f)
                break

    if not os.path.exists(path):
        manifest_path = os.path.join(reg.manifests_dir, f"{model_name}.json")
        if os.path.exists(manifest_path):
            import json
            with open(manifest_path, "r") as f:
                data = json.load(f)
                base = data.get("base_model", "")
                path = os.path.join(reg.models_dir, f"{base}.gguf") if not base.endswith(".gguf") else os.path.join(reg.models_dir, base)
                
    if os.path.exists(path):
        size_gb = os.path.getsize(path) / (1024**3)
        # Ensure we have VRAM capacity before loading
        if not engine_manager.air_swapper.ensure_vram_capacity(size_gb):
            raise Exception("Insufficient VRAM to load this model, even after eviction.")
            
        # Physically load it
        engine_manager.runtime.load_model(path)
        
        # Logically update the swapper
        if model_name in engine_manager.air_scheduler.active_models:
            if engine_manager.air_scheduler.active_models[model_name]["location"] != "VRAM":
                engine_manager.air_swapper.swap_to_vram(model_name)
        else:
            engine_manager.air_scheduler.register_model(model_name, "VRAM", size_gb, 0.0)
    engine_manager.air_scheduler.update_state(model_name, "Generating")
    
    def stream_air():
        import json
        try:
            for chunk in engine_manager.runtime.generate({"messages": req.messages}, stream=True):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            engine_manager.air_scheduler.update_state(model_name, "Keep Warm")
            
    return StreamingResponse(stream_air(), media_type="text/plain")

@app.get("/v1/models/list")
async def list_models():
    models = []
    for file in os.listdir(MODELS_DIR):
        if file.endswith(".gguf"):
            path = os.path.join(MODELS_DIR, file)
            size_gb = os.path.getsize(path) / (1024**3)
            models.append({
                "name": file.replace(".gguf", ""),
                "size_gb": round(size_gb, 2)
            })
    return {"models": models}

@app.get("/v1/models/ps")
async def ps_models():
    return engine_manager.cache.get_stats()

@app.get("/v1/models/info/{model_name}")
async def info_model(model_name: str):
    path = os.path.join(MODELS_DIR, f"{model_name}.gguf")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Model file not found")
    
    size_gb = os.path.getsize(path) / (1024**3)
    mod_time = os.path.getmtime(path)
    
    # Try to guess quantization from filename
    quant = "unknown"
    lower_name = model_name.lower()
    for q in ["q4_k_m", "q8_0", "f16", "q5_k_m", "q2_k"]:
        if q in lower_name:
            quant = q
            break
            
    return {
        "name": model_name,
        "path": path,
        "size_gb": round(size_gb, 2),
        "modified_timestamp": mod_time,
        "quantization": quant,
        "architecture": "llama" # Mocked for now
    }

@app.get("/v1/benchmark")
async def run_benchmark():
    try:
        from lmms.engine.benchmark import BenchmarkEngine
        # Mock 6GB VRAM for now
        results = BenchmarkEngine().run_benchmarks({"vram_total_mb": 6000})
        return {"status": "success", "benchmarks": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/v1/models/delete/{model_name}")
async def delete_model(model_name: str):
    path = os.path.join(MODELS_DIR, f"{model_name}.gguf")
    if engine_manager.runtime._is_loaded:
        engine_manager.cache.unload_model(model_name)
        engine_manager.runtime.unload_model()
    if os.path.exists(path):
        os.remove(path)
        return {"status": "success", "message": f"Deleted {model_name}"}
    raise HTTPException(status_code=404, detail="Model file not found")

@app.get("/v1/models/search")
async def search_models(q: str):
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        models = api.list_models(search=q, filter="gguf", limit=10)
        results = []
        for m in models:
            results.append({
                "modelId": m.id,
                "author": m.author or "Unknown",
                "downloads": getattr(m, "downloads", 0),
                "last_updated": str(getattr(m, "lastModified", "Unknown")),
                "gguf_available": True
            })
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/doctor")
async def engine_doctor(req: DoctorRequest):
    import sys
    import shutil
    
    report = {
        "engine_reachable": True,
        "models_dir_exists": os.path.exists(MODELS_DIR),
        "models_dir_writable": os.access(MODELS_DIR, os.W_OK) if os.path.exists(MODELS_DIR) else False,
        "python_version": sys.version.split(" ")[0],
        "cuda_support": False,
        "llama_cpp_python": False,
        "ram_available_gb": 0.0,
        "disk_available_gb": 0.0
    }
    
    try:
        import psutil
        report["ram_available_gb"] = round(psutil.virtual_memory().available / (1024**3), 2)
    except:
        pass
        
    if os.path.exists(MODELS_DIR):
        total, used, free = shutil.disk_usage(MODELS_DIR)
        report["disk_available_gb"] = round(free / (1024**3), 2)
        
    try:
        import llama_cpp
        report["llama_cpp_python"] = True
        import torch
        report["cuda_support"] = torch.cuda.is_available()
    except:
        pass
        
    fixes_applied = []
    if req.fix:
        if not report["models_dir_exists"]:
            os.makedirs(MODELS_DIR, exist_ok=True)
            report["models_dir_exists"] = True
            report["models_dir_writable"] = True
            fixes_applied.append("Created ~/.lmms/models/")
        
        if not report["cuda_support"]:
            fixes_applied.append("SUGGESTION: Run `CMAKE_ARGS='-DGGML_CUDA=on' pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir`")
            
        engine_manager.runtime.unload_model()
        fixes_applied.append("Cleared VRAM cache and unloaded models.")
        
    return {"report": report, "fixes": fixes_applied}

def download_model_task(model_name: str):
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        if "/" in model_name:
            repo_id = model_name
        else:
            # Map ollama tags to HF search
            search_term = model_name.replace(":", "-")
            models = list(api.list_models(search=search_term, filter="gguf", limit=1))
            if models:
                repo_id = models[0].id
            else:
                downloads_file = os.path.expanduser("~/.lmms/logs/downloads.json")
                try:
                    with open(downloads_file, "r") as f: state = json.load(f)
                    state[model_name] = {"status": "failed (not found)", "repo": model_name, "file": ""}
                    with open(downloads_file, "w") as f: json.dump(state, f)
                except Exception: pass
                print(f"Could not find any GGUF repo matching {model_name}")
                return
                
        files = api.list_repo_files(repo_id=repo_id)
        gguf_files = [f for f in files if f.endswith(".gguf")]
        if not gguf_files:
            print(f"No GGUF files found in {repo_id}")
            return
            
        target_file = gguf_files[0]
        for f in gguf_files:
            if "q4_k_m" in f.lower():
                target_file = f
                break
                
        print(f"Starting download for {repo_id}/{target_file}...")
        
        # Track active download
        downloads_file = os.path.expanduser("~/.lmms/logs/downloads.json")
        os.makedirs(os.path.dirname(downloads_file), exist_ok=True)
        state = {}
        if os.path.exists(downloads_file):
            try:
                with open(downloads_file, "r") as f:
                    state = json.load(f)
            except Exception: pass
            
        state[model_name] = {"status": "0%", "repo": repo_id, "file": target_file}
        with open(downloads_file, "w") as f:
            json.dump(state, f)
            
        # Force HF logging to INFO to ensure tqdm is not disabled
        import logging
        logging.getLogger("huggingface_hub").setLevel(logging.INFO)

        from huggingface_hub.utils import _tqdm
        original_tqdm = _tqdm.tqdm

        class DownloadTqdm(original_tqdm):
            def update(self, n=1):
                super().update(n)
                if hasattr(self, 'total') and self.total:
                    pct = int((self.n / self.total) * 100)
                    speed = getattr(self, 'format_dict', {}).get('rate', 0)
                    speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else ""
                    size_str = f"{self.n / 1024 / 1024 / 1024:.2f}G/{self.total / 1024 / 1024 / 1024:.2f}G"
                    
                    try:
                        with open(downloads_file, "r") as file: d = json.load(file)
                        d[model_name]["status"] = f"{pct}% ({size_str} @ {speed_str})"
                        with open(downloads_file, "w") as file: json.dump(d, file)
                    except Exception: pass

        _tqdm.tqdm = DownloadTqdm
        
        try:
            hf_hub_download(repo_id=repo_id, filename=target_file, local_dir=MODELS_DIR)
            
            # Set state to complete
            try:
                with open(downloads_file, "r") as f: state = json.load(f)
                state[model_name]["status"] = "complete"
                with open(downloads_file, "w") as f: json.dump(state, f)
            except Exception: pass
            
        finally:
            _tqdm.tqdm = original_tqdm # Restore original just in case
            
        print("Download complete.")
    except Exception as e:
        downloads_file = os.path.expanduser("~/.lmms/logs/downloads.json")
        try:
            with open(downloads_file, "r") as f: state = json.load(f)
            state[model_name] = {"status": "failed", "error": str(e)}
            with open(downloads_file, "w") as f: json.dump(state, f)
        except Exception: pass
        print(f"Download failed: {e}")

@app.post("/v1/models/pull")
async def pull_model(req: PullRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(download_model_task, req.model_name)
    return {"status": "downloading", "model": req.model_name}

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    # Ensure a model is loaded. If not, auto-load? The prompt says "Ensure real tokens stream"
    # LlamaCppRuntime has generate(context, stream=True)
    if req.model_name not in engine_manager.runtime._models and req.model_name + ".gguf" not in engine_manager.runtime._models and os.path.basename(req.model_name).replace(".gguf", "") not in engine_manager.runtime._models:
        # Try to auto-load if file exists
        path = os.path.join(MODELS_DIR, f"{req.model_name}.gguf")
        
        if not os.path.exists(path):
            try:
                downloads_file = os.path.expanduser("~/.lmms/logs/downloads.json")
                if os.path.exists(downloads_file):
                    with open(downloads_file, "r") as f: d = json.load(f)
                    if req.model_name in d and d[req.model_name].get("file"):
                        path = os.path.join(MODELS_DIR, d[req.model_name]["file"])
            except Exception: pass

        if not os.path.exists(path):
            search_term = req.model_name.replace(":", "-").lower()
            for f in os.listdir(MODELS_DIR):
                if f.endswith(".gguf") and search_term in f.lower():
                    path = os.path.join(MODELS_DIR, f)
                    break

        if os.path.exists(path):
            size_gb = os.path.getsize(path) / (1024**3)
            if engine_manager.cache.can_fit(size_gb):
                success = engine_manager.runtime.load_model(path)
                if not success:
                    raise HTTPException(status_code=500, detail="Failed to load model. Is llama-cpp-python installed?")
                engine_manager.cache.load_model(req.model_name, size_gb)
            else:
                raise HTTPException(status_code=507, detail="Insufficient memory to auto-load")
        else:
            raise HTTPException(status_code=404, detail="Model not loaded and file not found")
            
    if req.stream:
        async def event_generator():
            try:
                # generate yields {"message": {"content": "..."}}
                generator = engine_manager.runtime.generate({"messages": req.messages, "mode": req.mode, "think": req.think}, stream=True)
                for chunk in generator:
                    # chunk is dict, we yield SSE format
                    # data: {"content": "..."}
                    yield f"data: {json.dumps(chunk['message'])}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        return StreamingResponse(event_generator(), media_type="text/event-stream")
    else:
        response = engine_manager.runtime.generate({"messages": req.messages, "mode": req.mode, "think": req.think}, stream=False)
        return response




def run_server(port: int = 11435):
    print(f"LMMs Engine starting on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

if __name__ == "__main__":
    run_server()
