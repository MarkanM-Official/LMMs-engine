#!/usr/bin/env python3
"""
main.py — LMMs Engine Entry Point
Commands: lmms run, lmms ps, lmms stop, lmms list, etc.
"""

import sys
import os
import subprocess
import json

API_URL = "http://localhost:11435/v1"
def is_root():
    return os.geteuid() == 0

def ensure_server_running():
    import requests
    import time
    try:
        requests.get("http://localhost:11435/v1/health", timeout=1)
    except:
        print("Starting Engine daemon in the background...")
        log_file = os.path.expanduser("~/.lmms/logs/server.log")
        with open(log_file, "a") as f:
            subprocess.Popen([sys.executable, "main.py", "serve"], stdout=f, stderr=f)
        time.sleep(2)

def main():
    import sys
    import os
    base_dir = os.path.expanduser("~/.lmms")
    for subdir in ["models", "cache", "logs", "manifests", "workspaces"]:
        os.makedirs(os.path.join(base_dir, subdir), exist_ok=True)
    args = sys.argv[1:]
    
    if not args or args[0] in ("-h", "--help", "help"):
        print('''
LMMs Local AI Powerhouse
Usage: python main.py [command] [options]

Engine Commands:
  pull <model>      Download a model
  run <model>       Run a model interactively (-fast, -deep, -code, -research)
  stop <model>      Unload model from VRAM
  ps                Show loaded models and engine stats
  list              List downloaded models
  info <model>      Show model details
  rm <model>        Delete a model
  search <query>    Search for models
  doctor            Run engine health checks (--fix to auto-repair)
  benchmark         Run performance benchmarks
  serve             Start engine server in foreground
  create            Create model from Modelfile
  registry          Manage registries
  downloads         View active downloads
  cache             Manage VRAM cache directly

Air Commands:
  air ps            Show Air engine processes
  air cache         Show Air distributed cache
  air stats         Show Air swarm stats
  air unload        Unload all Air models
  air benchmark     Benchmark Air node

Launcher Commands:
  set --gui         Set default boot mode to GUI
  set --cli         Set default boot mode to CLI
  set --engine      Set default boot mode to Engine
''')
        sys.exit(0)

    # Engine Server
    if args and args[0] in ["engine", "serve"]:
        from lmms.api.server import run_server
        print("Starting LMMs Engine on port 11435...")
        run_server(11435)
        return

    # Parse args
    model_args = []
    mode_arg = "deep"
    prompt_parts = []
    is_air = False
    
    i = 0
    while i < len(args):
        if args[i] in ["--air", "-air"]:
            is_air = True
            i += 1
        elif args[i] == "run" and i + 1 < len(args):
            i += 1
            # Collect all models until we hit a flag or a prompt string
            while i < len(args) and not args[i].startswith("-") and args[i] not in ["fast", "deep", "code", "research"]:
                if " " in args[i] or args[i].lower() in ["hello", "hi"]:
                    break
                model_args.append(args[i])
                i += 1
            continue
        elif args[i] in ["-fast", "--fast", "fast"]:
            mode_arg = "fast"
            i += 1
        elif args[i] in ["-deep", "--deep", "deep"]:
            mode_arg = "deep"
            i += 1
        elif args[i] in ["-code", "--code", "code"]:
            mode_arg = "code"
            i += 1
        elif args[i] in ["-research", "--research", "research"]:
            mode_arg = "research"
            i += 1
        elif not args[i].startswith("--") and not args[i].startswith("-") and args[i] not in ["run", "list", "ps", "pull", "info", "benchmark", "rm", "stop", "search", "doctor", "cache", "air", "registry", "downloads", "create", "serve", "delete"]:
            prompt_parts.append(args[i])
            i += 1
        else:
            i += 1

    # Clean args for command router
    clean_args = [a for a in args if a not in ["--air", "-air"]]
    
    # Engine CLI Commands Bypass
    if clean_args and clean_args[0] in ["run", "list", "ps", "pull", "info", "benchmark", "rm", "delete", "stop", "search", "doctor", "cache", "air", "registry", "downloads", "create", "serve"]:
        import requests, json, sys
        cmd = clean_args[0]
        try:
            if cmd == "list":
                res = requests.get("http://localhost:11435/v1/models/list", timeout=5).json()
                from rich.table import Table
                from rich.console import Console
                c = Console()
                table = Table(title="LMMS Local Models")
                table.add_column("Model Name")
                table.add_column("Size (GB)")
                for m in res.get("models", []):
                    table.add_row(m["name"], str(m["size_gb"]))
                c.print(table)
                sys.exit(0)
            elif cmd == "info":
                if len(args) < 2:
                    print("Usage: lmms info <model_name>")
                    sys.exit(1)
                from lmms.engine.registry import RegistryManager
                reg = RegistryManager()
                reg.info_model(args[1])
                sys.exit(0)
            elif cmd == "benchmark":
                if len(args) < 2:
                    print("Usage: lmms benchmark <model_name>")
                    sys.exit(1)
                from lmms.engine.benchmark import BenchmarkEngine
                b = BenchmarkEngine()
                b.run_real_benchmark(args[1])
                sys.exit(0)
            elif cmd == "ps":
                ensure_server_running()
                res = requests.get(f"{API_URL}/models/ps", timeout=5).json()
                from rich.console import Console
                c = Console()
                c.print("[bold cyan]Engine Stats:[/bold cyan]")
                for k, v in res.items():
                    c.print(f"  {k}: {v}")
                sys.exit(0)
            elif cmd == "pull" and len(clean_args) > 1:
                model_name = clean_args[1]
                ensure_server_running()
                res = requests.post(f"{API_URL}/models/pull", json={"model_name": model_name}, timeout=5).json()
                print(f"Pulling {model_name}...")
                
                # Stream progress inline
                import time, sys
                f = os.path.expanduser("~/.lmms/logs/downloads.json")
                last_status = ""
                while True:
                    try:
                        with open(f, "r") as file: d = json.load(file)
                        if model_name in d:
                            status = d[model_name].get("status", "")
                            if status != last_status:
                                sys.stdout.write(f"\r\033[K[{model_name}] {status}")
                                sys.stdout.flush()
                                last_status = status
                            if "complete" in status.lower() or "failed" in status.lower():
                                print()
                                break
                    except Exception: pass
                    time.sleep(0.5)
                sys.exit(0)
            elif cmd == "stop" and len(clean_args) > 1:
                ensure_server_running()
                res = requests.post(f"{API_URL}/models/unload", json={"model_name": clean_args[1]}, timeout=5).json()
                print(f"Stopped and unloaded {clean_args[1]}.")
                sys.exit(0)
            elif cmd == "rm" and len(clean_args) > 1:
                ensure_server_running()
                res = requests.delete(f"{API_URL}/models/delete/{clean_args[1]}", timeout=5).json()
                print(f"Deleted {clean_args[1]}.")
                sys.exit(0)
            elif cmd == "search" and len(clean_args) > 1:
                ensure_server_running()
                res = requests.get(f"{API_URL}/models/search?q={clean_args[1]}", timeout=15).json()
                from rich.table import Table
                from rich.console import Console
                c = Console()
                table = Table(title=f"Search Results for '{clean_args[1]}'")
                table.add_column("Model")
                table.add_column("Author")
                table.add_column("Downloads")
                table.add_column("Last Updated")
                table.add_column("GGUF")
                for m in res.get("results", []):
                    table.add_row(m["modelId"], m["author"], str(m["downloads"]), m["last_updated"][:10], "✅" if m["gguf_available"] else "❌")
                c.print(table)
                sys.exit(0)
            elif cmd == "doctor":
                ensure_server_running()
                is_fix = "--fix" in clean_args
                res = requests.post(f"{API_URL}/doctor", json={"fix": is_fix}, timeout=15).json()
                from rich.table import Table
                from rich.console import Console
                c = Console()
                report = res.get("report", {})
                table = Table(title="Engine Doctor Report")
                table.add_column("Check")
                table.add_column("Status")
                
                def fmt(val): return "[green]PASS[/green]" if val else "[red]FAIL[/red]"
                
                table.add_row("Engine Reachable", fmt(report.get("engine_reachable")))
                table.add_row("Models Dir Exists", fmt(report.get("models_dir_exists")))
                table.add_row("Models Dir Writable", fmt(report.get("models_dir_writable")))
                table.add_row("CUDA Support", fmt(report.get("cuda_support")))
                table.add_row("Llama-CPP Python", fmt(report.get("llama_cpp_python")))
                table.add_row("Python Version", report.get("python_version", "Unknown"))
                table.add_row("RAM Available", f"{report.get('ram_available_gb', 0)} GB")
                table.add_row("Disk Available", f"{report.get('disk_available_gb', 0)} GB")
                c.print(table)
                sys.exit(0)
            elif cmd == "run" and model_args:
                ensure_server_running()
                def run_chat(messages, model_name):
                    try:
                        payload = {"model_name": model_name, "messages": messages, "stream": True, "mode": mode_arg}
                        if mode_arg == "fast": payload["think"] = False
                        elif mode_arg == "deep": payload["think"] = True
                        
                        endpoint = f"{API_URL}/air/generate" if is_air else f"{API_URL}/chat/completions"
                        res = requests.post(endpoint, json=payload, stream=True, timeout=120)
                        if res.status_code != 200:
                            print(f"\n[{model_name}] [Engine Error {res.status_code}] {res.text}")
                            return ""
                        reply = ""
                        for line in res.iter_lines():
                            if line:
                                decoded = line.decode('utf-8')
                                if decoded.startswith("data: "):
                                    data_str = decoded[6:]
                                    if data_str == "[DONE]": break
                                    try:
                                        data = json.loads(data_str)
                                        if "error" in data:
                                            print(f"\n[{model_name}] [Error] {data['error']}")
                                            break
                                        
                                        token = data.get("content", "")
                                        if not token and "choices" in data:
                                            token = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                        if not token and "message" in data:
                                            token = data.get("message", {}).get("content", "")
                                            
                                        if token:
                                            reply += token
                                            print(token, end="", flush=True)
                                    except Exception as e:
                                        print(f" [JSON parse error: {e}] ")
                        print()
                        return reply
                    except Exception as e:
                        print(f"\n[{model_name}] [Engine Error] {e}")
                        return ""

                if len(model_args) > 1:
                    import threading
                    
                    def thread_run_chat(messages, model_name, lock):
                        try:
                            payload = {"model_name": model_name, "messages": messages, "stream": True, "mode": mode_arg}
                            if mode_arg == "fast": payload["think"] = False
                            elif mode_arg == "deep": payload["think"] = True
                            
                            endpoint = f"{API_URL}/air/generate" if is_air else f"{API_URL}/chat/completions"
                            res = requests.post(endpoint, json=payload, stream=True, timeout=120)
                            if res.status_code != 200:
                                with lock:
                                    print(f"\n[{model_name}] [Engine Error {res.status_code}] {res.text}")
                                return
                                
                            reply = ""
                            buffer = ""
                            for line in res.iter_lines():
                                if line:
                                    decoded = line.decode('utf-8')
                                    if decoded.startswith("data: "):
                                        data_str = decoded[6:]
                                        if data_str == "[DONE]": break
                                        try:
                                            data = json.loads(data_str)
                                            token = data.get("content", "")
                                            if not token and "choices" in data:
                                                token = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                            if not token and "message" in data:
                                                token = data.get("message", {}).get("content", "")
                                                
                                            if token:
                                                reply += token
                                                buffer += token
                                                if len(buffer) > 20 or token.endswith("\n"):
                                                    with lock:
                                                        print(f"[{model_name}] {buffer}", end="", flush=True)
                                                    buffer = ""
                                        except Exception:
                                            pass
                            if buffer:
                                with lock:
                                    print(f"[{model_name}] {buffer}", end="", flush=True)
                                    print()
                        except Exception as e:
                            with lock:
                                print(f"\n[{model_name}] [Engine Error] {e}")

                    if prompt_parts:
                        messages = [{"role": "user", "content": " ".join(prompt_parts)}]
                        print(f"User: {messages[0]['content']}")
                        lock = threading.Lock()
                        threads = []
                        for m_arg in model_args:
                            t = threading.Thread(target=thread_run_chat, args=(messages, m_arg, lock))
                            threads.append(t)
                            t.start()
                        for t in threads:
                            t.join()
                        sys.exit(0)
                    else:
                        print(f"Started parallel engine session with {', '.join(model_args)} (Mode: {mode_arg})")
                        messages = []
                        while True:
                            try:
                                user_in = input(f"[Parallel]> ")
                                if not user_in.strip(): continue
                                if user_in.lower() in ["/exit", "/quit", "exit"]: break
                                messages.append({"role": "user", "content": user_in})
                                lock = threading.Lock()
                                threads = []
                                for m_arg in model_args:
                                    t = threading.Thread(target=thread_run_chat, args=(messages, m_arg, lock))
                                    threads.append(t)
                                    t.start()
                                for t in threads:
                                    t.join()
                                messages.append({"role": "assistant", "content": "(Parallel outputs hidden from history)"})
                            except (KeyboardInterrupt, EOFError):
                                print("\nExiting.")
                                break
                        sys.exit(0)
                else:
                    model_arg = model_args[0]
                    if prompt_parts:
                        messages = [{"role": "user", "content": " ".join(prompt_parts)}]
                        print(f"User: {messages[0]['content']}")
                        print(f"[{model_arg}] ", end="", flush=True)
                        run_chat(messages, model_arg)
                        sys.exit(0)
                    else:
                        print(f"Started interactive engine session with {model_arg} (Mode: {mode_arg})")
                        messages = []
                        while True:
                            try:
                                user_in = input(f"[{model_arg}]> ")
                                if not user_in.strip(): continue
                                if user_in.lower() in ["/exit", "/quit", "exit"]: break
                                messages.append({"role": "user", "content": user_in})
                                print(f"[{model_arg}] ", end="", flush=True)
                                reply = run_chat(messages, model_arg)
                                messages.append({"role": "assistant", "content": reply})
                            except (KeyboardInterrupt, EOFError):
                                print("\nExiting.")
                                break
                        sys.exit(0)
            elif cmd == "create":
                if len(clean_args) < 2:
                    print("Usage: lmms create <model_name> -f Modelfile")
                    sys.exit(1)
                
                model_name = clean_args[1]
                modelfile_path = "Modelfile"
                if "-f" in clean_args:
                    idx = clean_args.index("-f")
                    if idx + 1 < len(clean_args):
                        modelfile_path = clean_args[idx + 1]
                
                from lmms.engine.modelfile import ModelfileParser
                parser = ModelfileParser()
                parser.compile(modelfile_path, model_name)
                sys.exit(0)
            elif cmd == "registry":
                if len(clean_args) > 1 and clean_args[1] == "list":
                    from lmms.engine.registry import RegistryManager
                    reg = RegistryManager()
                    reg.list_models()
                elif len(clean_args) > 2 and clean_args[1] in ["rm", "delete"]:
                    from lmms.engine.registry import RegistryManager
                    reg = RegistryManager()
                    reg.rm_model(clean_args[2])
                else:
                    print("Usage: lmms registry [list|rm]")
                sys.exit(0)
            elif cmd == "downloads":
                f = os.path.expanduser("~/.lmms/logs/downloads.json")
                if not os.path.exists(f):
                    print("No active downloads.")
                    return
                with open(f, "r") as file:
                    d = json.load(file)
                
                print(f"{'LMMs Active Downloads':^80}")
                print("┏" + "━"*32 + "┳" + "━"*32 + "┳" + "━"*33 + "┳" + "━"*16 + "┓")
                print(f"┃ {'MODEL':<30} ┃ {'REPO':<30} ┃ {'FILE':<31} ┃ {'STATUS':<14} ┃")
                print("┡" + "━"*32 + "╇" + "━"*32 + "╇" + "━"*33 + "╇" + "━"*16 + "┩")
                
                for k, v in d.items():
                    m = (k[:28] + '..') if len(k) > 30 else k
                    r = (v.get("repo", "")[:28] + '..') if len(v.get("repo", "")) > 30 else v.get("repo", "")
                    fi = (v.get("file", "")[:29] + '..') if len(v.get("file", "")) > 31 else v.get("file", "")
                    s = v.get("status", "")[:14]
                    print(f"│ {m:<30} │ {r:<30} │ {fi:<31} │ {s:<14} │")
                
                print("└" + "─"*32 + "┴" + "─"*32 + "┴" + "─"*33 + "┴" + "─"*16 + "┘")
                sys.exit(0)
            elif cmd == "cache":
                if len(args) > 1 and args[1] == "list":
                    try:
                        ensure_server_running()
                        res = requests.get(f"{API_URL}/models/ps", timeout=2).json()
                        from rich.console import Console
                        c = Console()
                        c.print("[bold cyan]LMMs Cache Stats (VRAM/RAM):[/bold cyan]")
                        for k, v in res.items():
                            c.print(f"  {k}: {v}")
                    except Exception as e:
                        print(f"Engine server is offline. Cannot read live VRAM cache. Error: {e}")
                else:
                    print("Usage: lmms cache list")
                sys.exit(0)
            elif cmd == "air":
                if len(clean_args) > 1 and clean_args[1] == "ps":
                    try:
                        ensure_server_running()
                        res = requests.get(f"{API_URL}/air/ps", timeout=2).json()
                        from rich.console import Console
                        from rich.table import Table
                        c = Console()
                        table = Table(title="Air Managed Models")
                        table.add_column("Model")
                        table.add_column("State")
                        table.add_column("VRAM (GB)")
                        table.add_column("RAM (GB)")
                        table.add_column("Last Used")
                        import time
                        for m in res:
                            table.add_row(m["model"], m["state"], str(m["vram_gb"]), str(m["ram_gb"]), time.ctime(m["last_used"]))
                        c.print(table)
                    except Exception as e:
                        print(f"Engine server offline or Air disabled. Error: {e}")
                    sys.exit(0)
                elif len(clean_args) > 1 and clean_args[1] == "cache":
                    try:
                        ensure_server_running()
                        res = requests.get(f"{API_URL}/air/cache", timeout=2).json()
                        from rich.console import Console
                        c = Console()
                        c.print("[bold cyan]Air Cache Topology:[/bold cyan]")
                        c.print(f"  [green]VRAM Models:[/green] {', '.join(res.get('vram_models', [])) or 'None'}")
                        c.print(f"  [yellow]RAM Models:[/yellow]  {', '.join(res.get('ram_models', [])) or 'None'}")
                        c.print(f"  [blue]Disk Models:[/blue] {', '.join(res.get('disk_models', [])) or 'None'}")
                    except Exception as e:
                        print(f"Engine server offline or Air disabled. Error: {e}")
                    sys.exit(0)
                elif len(clean_args) > 1 and clean_args[1] == "stats":
                    try:
                        ensure_server_running()
                        res = requests.get(f"{API_URL}/air/stats", timeout=2).json()
                        from rich.console import Console
                        from rich.table import Table
                        c = Console()
                        table = Table(title="Air System Stats")
                        table.add_column("Metric", style="cyan")
                        table.add_column("Value", style="green")
                        for k, v in res.items():
                            table.add_row(k, str(v))
                        c.print(table)
                    except Exception as e:
                        print(f"Engine server offline. Error: {e}")
                    sys.exit(0)
                else:
                    print("Usage: lmms air [ps|stats|cache]")
                    sys.exit(1)
            else:
                print(f"Unknown command: {cmd}")
                sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"\n[Engine Error] Could not connect to Engine at localhost:11435. ({e})")
            sys.exit(1)

if __name__ == "__main__":
    main()
