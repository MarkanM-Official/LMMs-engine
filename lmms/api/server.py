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
async def unload_model(req: UnloadRequest):
    engine_manager.cache.unload_model(req.model_name)
    engine_manager.runtime.unload_model()
    return {"status": "success", "stats": engine_manager.cache.get_stats()}

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
        repo_id = model_name
        
        if "/" not in model_name:
            models = list(api.list_models(search=model_name, filter="gguf", limit=1))
            if models:
                repo_id = models[0].id
            else:
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
            
        state[model_name] = {"status": "downloading", "repo": repo_id, "file": target_file}
        with open(downloads_file, "w") as f:
            json.dump(state, f)
            
        hf_hub_download(repo_id=repo_id, filename=target_file, local_dir=MODELS_DIR)
        
        state[model_name] = {"status": "complete", "repo": repo_id, "file": target_file}
        with open(downloads_file, "w") as f:
            json.dump(state, f)
            
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
    if not engine_manager.runtime._is_loaded:
        # Try to auto-load if file exists
        path = os.path.join(MODELS_DIR, f"{req.model_name}.gguf")
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
