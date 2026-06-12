#!/usr/bin/env python3
"""
main.py — LMMs Engine Entry Point
Commands: lmms run, lmms ps, lmms stop, lmms list, etc.
"""

import sys
import os
import subprocess
import json

def is_root():
    return os.geteuid() == 0

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
    model_arg = None
    mode_arg = "deep"
    prompt_parts = []
    
    i = 0
    while i < len(args):
        if args[i] == "run" and i + 1 < len(args):
            model_arg = args[i + 1]
            i += 2
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

    # Engine CLI Commands Bypass
    if args and args[0] in ["run", "list", "ps", "pull", "info", "benchmark", "rm", "delete", "stop", "search", "doctor", "cache", "air", "registry", "downloads", "create", "serve"]:
        import requests, json, sys
        cmd = args[0]
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
                res = requests.get("http://localhost:11435/v1/models/ps", timeout=5).json()
                from rich.console import Console
                c = Console()
                c.print("[bold cyan]Engine Stats:[/bold cyan]")
                for k, v in res.items():
                    c.print(f"  {k}: {v}")
                sys.exit(0)
            elif cmd == "pull" and len(args) > 1:
                res = requests.post("http://localhost:11435/v1/models/pull", json={"model_name": args[1]}, timeout=5).json()
                print(f"Pulling {args[1]}... Check engine logs for progress.")
                sys.exit(0)
            elif cmd == "stop" and len(args) > 1:
                res = requests.post("http://localhost:11435/v1/models/unload", json={"model_name": args[1]}, timeout=5).json()
                print(f"Stopped and unloaded {args[1]}.")
                sys.exit(0)
            elif cmd == "rm" and len(args) > 1:
                res = requests.delete(f"http://localhost:11435/v1/models/delete/{args[1]}", timeout=5).json()
                print(f"Deleted {args[1]}.")
                sys.exit(0)
            elif cmd == "search" and len(args) > 1:
                res = requests.get(f"http://localhost:11435/v1/models/search?q={args[1]}", timeout=15).json()
                from rich.table import Table
                from rich.console import Console
                c = Console()
                table = Table(title=f"Search Results for '{args[1]}'")
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
                is_fix = "--fix" in args
                res = requests.post("http://localhost:11435/v1/doctor", json={"fix": is_fix}, timeout=15).json()
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
            elif cmd == "run" and model_arg:
                def run_chat(messages):
                    try:
                        print("Assistant: ", end="", flush=True)
                        payload = {"model_name": model_arg, "messages": messages, "stream": True, "mode": mode_arg}
                        if mode_arg == "fast": payload["think"] = False
                        elif mode_arg == "deep": payload["think"] = True
                        res = requests.post("http://localhost:11435/v1/chat/completions", json=payload, stream=True, timeout=120)
                        if res.status_code != 200:
                            print(f"\n[Engine Error {res.status_code}] {res.text}")
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
                                            print(f"\n[Error] {data['error']}")
                                            break
                                        
                                        # Support both OpenAI schema and custom native schema
                                        token = data.get("content", "")
                                        if not token and "choices" in data:
                                            token = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                            
                                        if token:
                                            reply += token
                                            print(token, end="", flush=True)
                                    except Exception as e:
                                        print(f" [JSON parse error: {e}] ")
                        print()
                        return reply
                    except Exception as e:
                        print(f"\n[Engine Error] {e}")
                        return ""

                if prompt_parts:
                    messages = [{"role": "user", "content": " ".join(prompt_parts)}]
                    print(f"User: {messages[0]['content']}")
                    run_chat(messages)
                    sys.exit(0)
                else:
                    # Interactive Engine REPL
                    print(f"Started interactive engine session with {model_arg} (Mode: {mode_arg})")
                    messages = []
                    while True:
                        try:
                            user_in = input(f"[{model_arg}]> ")
                            if not user_in.strip(): continue
                            if user_in.lower() in ["/exit", "/quit", "exit"]: break
                            messages.append({"role": "user", "content": user_in})
                            reply = run_chat(messages)
                            messages.append({"role": "assistant", "content": reply})
                        except (KeyboardInterrupt, EOFError):
                            break
                    sys.exit(0)
            elif cmd == "create":
                if "-f" not in args or len(args) < 3:
                    print("Usage: lmms create <model_name> -f <Modelfile>")
                    sys.exit(1)
                
                # lmms create model_name -f Modelfile
                f_index = args.index("-f")
                modelfile_path = args[f_index + 1]
                model_name = args[1] if f_index > 1 else args[3]
                
                from lmms.engine.modelfile import ModelfileParser
                parser = ModelfileParser()
                try:
                    parser.create(model_name, modelfile_path)
                except Exception as e:
                    print(f"Error creating model: {e}")
                    sys.exit(1)
                sys.exit(0)
            elif cmd == "registry":
                if len(args) < 2:
                    print("Usage: lmms registry [list|rm]")
                    sys.exit(1)
                
                from lmms.engine.registry import RegistryManager
                reg = RegistryManager()
                if args[1] == "list":
                    reg.list_models()
                elif args[1] in ["rm", "delete"] and len(args) > 2:
                    reg.rm_model(args[2])
                else:
                    print(f"Unknown registry command: {args[1]}")
                sys.exit(0)
            elif cmd == "downloads":
                from lmms.engine.downloads_manager import DownloadsManager
                dm = DownloadsManager()
                dm.show_downloads()
                sys.exit(0)
            elif cmd == "cache":
                if len(args) > 1 and args[1] == "list":
                    try:
                        res = requests.get("http://localhost:11435/v1/models/ps", timeout=2).json()
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
                if len(args) > 1 and args[1] == "ps":
                    print("Air subsystem not implemented")
                else:
                    print(f"Air command '{args}' not fully implemented natively yet.")
                sys.exit(0)
            else:
                print(f"Unknown command: {cmd}")
                sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"\n[Engine Error] Could not connect to Engine at localhost:11435. ({e})")
            sys.exit(1)

if __name__ == "__main__":
    main()
