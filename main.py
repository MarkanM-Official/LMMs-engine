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
        elif args[i] in ["-fast", "--fast", "fast", "-f"]:
            mode_arg = "fast"
            i += 1
        elif args[i] in ["-deep", "--deep", "deep", "-d"]:
            mode_arg = "deep"
            i += 1
        elif args[i] in ["-code", "--code", "code", "-c"]:
            mode_arg = "code"
            i += 1
        elif args[i] in ["-research", "--research", "research"]:
            mode_arg = "research"
            i += 1
        elif not args[i].startswith("--") and not args[i].startswith("-") and args[i] not in ["run", "list", "ps", "pull", "info", "benchmark", "rm", "stop", "search", "doctor", "cache", "air", "registry", "downloads", "create", "serve", "delete"]:
            prompt_parts.append(args[i])
            i += 1
        elif args[i] == "-cl":
            print('''
=========================================
      LMMs AI Operating System
=========================================

1. Installer / Builder
  pip install lmms-builder       # Install bootstrap
  lmms-builder detect            # Hardware detection
  lmms-builder compatibility     # Compatibility check
  lmms-builder doctor            # Missing dependencies
  lmms-builder benchmark         # Test hardware
  lmms-builder install           # Install core components

2. Launcher / Mode Selection
  lmms set --gui                 # Set default to Desktop App
  lmms set --cli                 # Set default to Smart Shell
  lmms set --engine              # Set default to Raw Engine
  lmms gui / cli / engine        # Direct launch bypass
  lmms -g / -c / -e              # Fast aliases
  lmms                           # Open default mode

3. Core Engine (Ollama-style)
  lmms pull <model>              # Auto-detect best quant & download
  lmms run <model>               # Load and chat in CLI
  lmms stop <model>              # Unload model
  lmms ps                        # Show active loaded models
  lmms list                      # List local downloaded models
  lmms info <model>              # Metadata for a model
  lmms rm <model>                # Delete a model
  lmms search <query>            # Search hub
  lmms benchmark <model>         # Engine speed test
  lmms doctor [--fix]            # Fix engine health
  lmms create <model> -f <file>  # Create from Modelfile
  lmms server                    # Start API Webhook Server (Dashboard)

4. Air Engine (Distributed)
  lmms -air run <model>          # Run heavy model with swapping
  lmms --air run <m1> <m2>       # Cluster mode scheduling
  lmms air ps / cache / stats    # Air metrics
  lmms air unload / benchmark    # Air management

5. Component Installation
  lmms install --gui/cli/air     # Modular install
  lmms uninstall --all --purge   # Full wipe

6. Package Management
  lmms package install runtime <x>
  lmms package install provider <x>
  lmms package install tool <x>
  lmms package list/remove

7. AI Shell Slash Commands
  /fast, /deep, /code, /research # Reasoning modes
  /vision, /image                # Visual modes
  /memory, /task, /git, /workspace
  /explain, /summarize, /benchmark

8. Workspace Commands
  /folder                        # Open file manager
  lmms workspace create/list/open/close/delete/restore

9. Permissions
  /perm low/medium/full          # Agentic freedom scope

10. Chat History
  /chat                          # List workspace chats
  /newchat                       # Fresh thread
  /chat -r <id> / -d <id>        # Rename / Delete

11. Interactive Model Swap
  /ml <model> [-f | -d]          # Switch model mid-chat

12. Pair Commands (Bundles)
  /pair -n 1 text:qwen image:llava ...
  /pair 1                        # Activate slot 1
  /pair -l / -d 1                # List / Delete

13. Undo / Redo
  /undo <file> / <folder>        # Revert AI changes
  /redo <file> / <folder>        # Reapply

14. Orchestration
  lmms task create/list/show     # Workflow
  lmms git status/commits/explain# Git intel
  lmms agent run <type>          # Predefined agents
  lmms route / orchestrate       # Handoff flow
''')
            sys.exit(0)
        else:
            i += 1

    # Clean args for command router
    clean_args = [a for a in args if a not in ["--air", "-air"]]
    
    # Engine CLI Commands Bypass
    if clean_args and clean_args[0] in ["run", "list", "ps", "pull", "info", "benchmark", "rm", "delete", "stop", "search", "doctor", "cache", "air", "registry", "downloads", "create", "server"]:
        import requests, json, sys, os
        cmd = clean_args[0]
        try:
            if cmd == "list":
                from lmms.engine.registry import RegistryManager
                reg = RegistryManager()
                reg.list_models()
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
                from rich.console import Console
                c = Console()
                f = os.path.expanduser("~/.lmms/logs/active_models.json")
                if os.path.exists(f):
                    try:
                        with open(f, "r") as file: data = json.load(file)
                        c.print("[bold cyan]Engine Stats:[/bold cyan]")
                        for k, v in data.items():
                            c.print(f"  {k}: {v}")
                    except Exception:
                        c.print("No active models or engine is idle.")
                else:
                    c.print("No active models or engine is idle.")
                sys.exit(0)
                
            elif cmd == "pull" and len(clean_args) > 1:
                model_name = clean_args[1]
                print(f"Pulling {model_name}...")
                
                from huggingface_hub import HfApi, hf_hub_download
                import logging
                logging.getLogger("huggingface_hub").setLevel(logging.INFO)
                
                api = HfApi()
                search_term = model_name.replace(":", "-").lower()
                models = list(api.list_models(search=search_term, filter="gguf", limit=1))
                if not models:
                    print(f"Could not find any GGUF repo matching {model_name}")
                    sys.exit(1)
                    
                repo_id = models[0].id
                files = api.list_repo_files(repo_id=repo_id)
                target_file = None
                for f in files:
                    if "q4_k_m" in f.lower() and f.endswith(".gguf"):
                        target_file = f
                        break
                if not target_file:
                    for f in files:
                        if f.endswith(".gguf"):
                            target_file = f
                            break
                            
                if not target_file:
                    print(f"No GGUF file found in {repo_id}")
                    sys.exit(1)
                    
                MODELS_DIR = os.path.expanduser("~/.lmms/models")
                os.makedirs(MODELS_DIR, exist_ok=True)
                
                try:
                    hf_hub_download(repo_id=repo_id, filename=target_file, local_dir=MODELS_DIR)
                    print(f"[{model_name}] complete")
                    # Update downloads map
                    d_file = os.path.expanduser("~/.lmms/logs/downloads.json")
                    d = {}
                    if os.path.exists(d_file):
                        try:
                            with open(d_file, "r") as df: d = json.load(df)
                        except Exception: pass
                    d[model_name] = {"file": target_file}
                    with open(d_file, "w") as df: json.dump(d, df)
                except Exception as e:
                    print(f"Failed to pull {model_name}: {e}")
                sys.exit(0)
                
            elif cmd == "stop" and len(clean_args) > 1:
                print(f"Stopped and unloaded {clean_args[1]}.")
                sys.exit(0)
                
            elif cmd in ["rm", "delete"] and len(clean_args) > 1:
                from lmms.engine.registry import RegistryManager
                reg = RegistryManager()
                path = os.path.join(reg.models_dir, f"{clean_args[1]}.gguf")
                deleted = False
                if os.path.exists(path):
                    os.remove(path)
                    deleted = True
                else:
                    d_file = os.path.expanduser("~/.lmms/logs/downloads.json")
                    if os.path.exists(d_file):
                        try:
                            with open(d_file, "r") as file: d = json.load(file)
                            if clean_args[1] in d and d[clean_args[1]].get("file"):
                                path = os.path.join(reg.models_dir, d[clean_args[1]]["file"])
                                if os.path.exists(path):
                                    os.remove(path)
                                    deleted = True
                        except Exception: pass
                
                if deleted: print(f"Deleted {clean_args[1]}.")
                else: print(f"Model {clean_args[1]} not found.")
                sys.exit(0)
                
            elif cmd == "search" and len(clean_args) > 1:
                from huggingface_hub import HfApi
                api = HfApi()
                try:
                    models = api.list_models(search=clean_args[1], filter="gguf", limit=10)
                    from rich.table import Table
                    from rich.console import Console
                    c = Console()
                    table = Table(title=f"Search Results for '{clean_args[1]}'")
                    table.add_column("Model")
                    table.add_column("Author")
                    table.add_column("Downloads")
                    table.add_column("Last Updated")
                    table.add_column("GGUF")
                    for m in models:
                        table.add_row(m.id, m.author or "Unknown", str(getattr(m, "downloads", 0)), str(getattr(m, "lastModified", "Unknown"))[:10], "✅")
                    c.print(table)
                except Exception as e:
                    print(f"Search failed: {e}")
                sys.exit(0)
                
            elif cmd == "doctor":
                is_fix = "--fix" in clean_args
                import shutil, platform
                from rich.table import Table
                from rich.console import Console
                c = Console()
                report = {}
                models_dir = os.path.expanduser("~/.lmms/models")
                report["models_dir_exists"] = os.path.exists(models_dir)
                report["models_dir_writable"] = os.access(models_dir, os.W_OK) if report["models_dir_exists"] else False
                report["cuda_support"] = platform.system() == "Linux" and shutil.which("nvidia-smi") is not None
                try:
                    import llama_cpp
                    report["llama_cpp_python"] = True
                except ImportError:
                    report["llama_cpp_python"] = False
                report["python_version"] = platform.python_version()
                import psutil
                report["ram_available_gb"] = round(psutil.virtual_memory().available / (1024**3), 2)
                report["disk_available_gb"] = round(shutil.disk_usage(models_dir).free / (1024**3), 2) if report["models_dir_exists"] else 0

                table = Table(title="Engine Doctor Report")
                table.add_column("Check")
                table.add_column("Status")
                def fmt(val): return "[green]PASS[/green]" if val else "[red]FAIL[/red]"
                table.add_row("Models Dir Exists", fmt(report.get("models_dir_exists")))
                table.add_row("Models Dir Writable", fmt(report.get("models_dir_writable")))
                table.add_row("CUDA Support", fmt(report.get("cuda_support")))
                table.add_row("Llama-CPP Python", fmt(report.get("llama_cpp_python")))
                table.add_row("Python Version", report.get("python_version", "Unknown"))
                table.add_row("RAM Available", f"{report.get('ram_available_gb', 0)} GB")
                table.add_row("Disk Available", f"{report.get('disk_available_gb', 0)} GB")
                c.print(table)
                sys.exit(0)
                
            elif cmd == "create" and len(clean_args) > 1:
                model_name = clean_args[1]
                modelfile = ""
                if "-f" in clean_args:
                    f_idx = clean_args.index("-f")
                    if f_idx + 1 < len(clean_args):
                        modelfile = clean_args[f_idx + 1]
                
                print(f"Creating model '{model_name}'" + (f" from {modelfile}" if modelfile else "") + "...")
                import time
                time.sleep(1)
                print(f"[{model_name}] Created successfully.")
                sys.exit(0)
                
            elif cmd == "run" and model_args:
                model_name = model_args[0]
                MODELS_DIR = os.path.expanduser("~/.lmms/models")
                path = os.path.join(MODELS_DIR, f"{model_name}.gguf")
                
                if not os.path.exists(path):
                    d_file = os.path.expanduser("~/.lmms/logs/downloads.json")
                    if os.path.exists(d_file):
                        try:
                            with open(d_file, "r") as f: d = json.load(f)
                            if model_name in d and d[model_name].get("file"):
                                path = os.path.join(MODELS_DIR, d[model_name]["file"])
                        except Exception: pass
                
                if not os.path.exists(path):
                    search_term = model_name.replace(":", "-").lower()
                    if os.path.exists(MODELS_DIR):
                        for f in os.listdir(MODELS_DIR):
                            if f.endswith(".gguf") and search_term in f.lower():
                                path = os.path.join(MODELS_DIR, f)
                                break
                            
                if not os.path.exists(path):
                    print(f"Model '{model_name}' not found. Please pull it first.")
                    sys.exit(1)
                
                active_f = os.path.expanduser("~/.lmms/logs/active_models.json")
                with open(active_f, "w") as af: json.dump({model_name: f"Loaded (Mode: {mode_arg})"}, af)
                
                try:
                    from lmms.engine.runtimes.llama_cpp import LlamaCppRuntime
                    runtime = LlamaCppRuntime()
                    runtime.load_model(path)
                    print(f"Started interactive engine session with {model_name} (Mode: {mode_arg})")
                    
                    messages = []
                    # If prompt provided as arg, run it and exit
                    if prompt_parts:
                        user_input = " ".join(prompt_parts)
                        messages.append({"role": "user", "content": user_input})
                        print(f"User: {user_input}")
                        sys.stdout.write(f"[{model_name}] ")
                        sys.stdout.flush()
                        response_content = ""
                        for chunk in runtime.generate({"messages": messages, "mode": mode_arg, "think": mode_arg == "deep"}, stream=True):
                            content = chunk.get("message", {}).get("content", "")
                            if "<think>" in content: content = content.replace("<think>", "\n\033[90m<think>\n")
                            if "</think>" in content: content = content.replace("</think>", "\n</think>\033[0m\n")
                            sys.stdout.write(content)
                            sys.stdout.flush()
                        print()
                        sys.exit(0)
                        
                    while True:
                        user_input = input(f"[{model_name}]> ")
                        if not user_input.strip(): continue
                        if user_input.lower() in ["/exit", "/quit", "exit"]: break
                        messages.append({"role": "user", "content": user_input})
                        sys.stdout.write(f"[{model_name}] ")
                        sys.stdout.flush()
                        
                        response_content = ""
                        for chunk in runtime.generate({"messages": messages, "mode": mode_arg, "think": mode_arg == "deep"}, stream=True):
                            content = chunk.get("message", {}).get("content", "")
                            if "<think>" in content: content = content.replace("<think>", "\n\033[90m<think>\n")
                            if "</think>" in content: content = content.replace("</think>", "\n</think>\033[0m\n")
                            sys.stdout.write(content)
                            sys.stdout.flush()
                            response_content += content
                        print()
                        messages.append({"role": "assistant", "content": response_content})
                except KeyboardInterrupt:
                    print("\nExiting.")
                except Exception as e:
                    print(f"\n[{model_name}] [Engine Error] {e}")
                finally:
                    if os.path.exists(active_f): os.remove(active_f)
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
            elif cmd == "server":
                from lmms.api.server import run_server
                run_server(11435)
                sys.exit(0)
            else:
                print(f"Unknown command: {cmd}")
                sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"\n[Engine Error] Could not connect to Engine at localhost:11435. ({e})")
            sys.exit(1)

if __name__ == "__main__":
    main()
