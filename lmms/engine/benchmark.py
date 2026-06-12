import time
from typing import Dict, Any
from rich.console import Console
from rich.table import Table

class BenchmarkEngine:
    def run_real_benchmark(self, model_name: str):
        c = Console()
        c.print(f"[cyan]Starting benchmark for {model_name}...[/cyan]")
        
        from lmms.engine.manager import engine_manager as engine
        
        import os
        from lmms.api.server import MODELS_DIR
        path = os.path.join(MODELS_DIR, f"{model_name}.gguf")
        if not os.path.exists(path):
            c.print(f"[red]Model {model_name} not found.[/red]")
            return
            
        size_gb = os.path.getsize(path) / (1024**3)
        
        # Measure Load Time
        t0 = time.time()
        try:
            success = engine.runtime.load_model(path)
            if not success:
                c.print("[red]Failed to load model.[/red]")
                return
            engine.cache.load_model(model_name, size_gb)
        except Exception as e:
            c.print(f"[red]Failed to load: {e}[/red]")
            return
        load_time = time.time() - t0
        
        # Measure Memory
        stats = engine.cache.get_stats()
        vram_used = stats["used_gb"]
        
        # Measure Tokens/Sec
        t1 = time.time()
        # Generate 10 tokens
        gen = engine.runtime.generate({"messages": [{"role": "user", "content": "Write a long poem."}], "mode": "fast", "think": False}, stream=True)
        tokens_generated = 0
        for chunk in gen:
            tokens_generated += 1
            if tokens_generated >= 10:
                break
        gen_time = time.time() - t1
        
        tok_sec = tokens_generated / gen_time if gen_time > 0 else 0
        
        # Unload
        engine.runtime.unload_model()
        engine.cache.unload_model(model_name)
        
        # Print
        table = Table(title=f"Benchmark: {model_name}")
        table.add_column("Metric", style="cyan")
        table.add_column("Result", style="green")
        table.add_row("Load Time", f"{load_time:.2f} s")
        table.add_row("Tokens/sec", f"{tok_sec:.2f} t/s")
        table.add_row("VRAM Used", f"{vram_used:.2f} GB")
        table.add_row("Device", stats["device"])
        
        c.print(table)

