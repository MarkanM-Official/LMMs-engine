"""
models.py — LMMs Model Manager (Full Rewrite)
Handles: Ollama, AirLLM, Cloud APIs, HuggingFace download (non-blocking)
"""

import requests
import json
import os
import subprocess
import time
import threading




class ModelManager:
    def __init__(self):
        self.text_model = "qwen3:8b"
        self.vision_model = "gemma4"
        self.base_url = "http://localhost:11434"
        self.active_models = set()
        self._download_thread = None
        self._download_status = {}

        self.local_models_dir = os.path.expanduser("~/.lmms/models/")
        os.makedirs(self.local_models_dir, exist_ok=True)

    # ──────────────────────────────────────────────
    # OLLAMA
    # ──────────────────────────────────────────────

    def set_model(self, model_name: str):
        if not model_name:
            return
        model_name = model_name.replace("ollama/", "")
        self.text_model = model_name
        try:
            requests.post("http://localhost:11435/v1/models/load", json={"model_name": self.text_model}, timeout=10)
        except Exception:
            pass

    def list_available(self):
        try:
            r = requests.get("http://localhost:11435/v1/models/list", timeout=2)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    def is_engine_running(self):
        try:
            r = requests.get("http://localhost:11435/v1/models/list", timeout=2)
            return r.status_code == 200
        except Exception:
            return False

    def unload_model(self, model_name: str):
        try:
            requests.post("http://localhost:11435/v1/models/unload", json={"model_name": model_name}, timeout=2)
        except Exception:
            pass

    # ──────────────────────────────────────────────
    # STATUS TABLE  (used by --status & /models)
    # ──────────────────────────────────────────────

    def get_model_status_table(self):
        from rich.table import Table
        table = Table(show_header=True, header_style="bold magenta", border_style="cyan")
        table.add_column("Type", style="dim", min_width=14)
        table.add_column("Name", style="bold cyan", min_width=20)
        table.add_column("Size", justify="right", min_width=7)
        table.add_column("Status", min_width=18)
        table.add_column("Permission", min_width=12)

        # 1. LMMS Engine Models
        try:
            r = requests.get("http://localhost:11435/v1/models/list", timeout=2)
            ps = requests.get("http://localhost:11435/v1/models/ps", timeout=2)
            active_names = []
            if ps.status_code == 200:
                active_names = [m["name"] for m in ps.json().get("models", [])]
            if r.status_code == 200:
                for m in r.json().get("models", []):
                    size_gb = m.get("size_gb", 0)
                    name = m["name"]
                    if name == self.text_model:
                        status = "[bold green]⚡ ACTIVE[/bold green]"
                    elif name in active_names:
                        status = "[yellow]💤 idle[/yellow]"
                    else:
                        status = "[dim]○ available[/dim]"
                    perm = "[green]full[/green]"
                    table.add_row("LMMS ENGINE", name, f"{size_gb:.1f}GB", status, perm)
        except Exception:
            table.add_row("LMMS ENGINE", "[red]Engine not running[/red]", "-", "[red]✗ offline[/red]", "-")

        # 2. Local GGUF Models
        if os.path.exists(self.local_models_dir):
            for file in os.listdir(self.local_models_dir):
                if file.endswith(".gguf"):
                    size_gb = os.path.getsize(os.path.join(self.local_models_dir, file)) / (1024 ** 3)
                    table.add_row("LOCAL-GGUF", file, f"{size_gb:.1f}GB", "[dim]○ available[/dim]", "[yellow]read[/yellow]")

        # 3. Cloud Connectors
        connectors = self._load_connectors()
        for name, data in connectors.items():
            table.add_row(
                "CLOUD-API",
                data.get("model_name", name),
                "-",
                "[green]🔌 connected[/green]",
                "[cyan]api-key[/cyan]",
            )

        # 4. AirLLM
        table.add_row("AIRLLM", "Any HF Model (70B+)", "-", "[dim]☁ available[/dim]", "[yellow]disk-only[/yellow]")

        # 5. Active downloads
        for model_name, status in self._download_status.items():
            table.add_row("HF-DOWNLOAD", model_name, "-", f"[yellow]{status}[/yellow]", "-")

        return table

    # ──────────────────────────────────────────────
    # HUGGINGFACE DOWNLOAD (non-blocking thread)
    # ──────────────────────────────────────────────

    def download_huggingface_model(self, query: str, console=None):
        """Search HF for GGUF models and download in background thread."""
        from rich.console import Console as RConsole
        c = console or RConsole()

        try:
            from huggingface_hub import HfApi, hf_hub_download
        except ImportError:
            c.print("[red]huggingface_hub not installed. Run /autoset[/red]")
            return

        api = HfApi()
        c.print(f"[cyan]Searching HuggingFace for: {query}...[/cyan]")
        try:
            results = list(api.list_models(search=query, limit=10, filter="gguf"))
        except Exception as e:
            c.print(f"[red]HF search failed: {e}[/red]")
            return

        if not results:
            c.print("[yellow]No GGUF models found on HuggingFace.[/yellow]")
            return

        c.print("\n[bold]Found Models:[/bold]")
        for i, m in enumerate(results):
            c.print(f"  [{i}] [cyan]{m.id}[/cyan]")

        try:
            choice = input("\nSelect model number (or 'q' to cancel): ").strip()
            if choice.lower() == "q":
                c.print("[dim]Cancelled.[/dim]")
                return
            idx = int(choice)
            selected_repo = results[idx].id
        except (ValueError, IndexError, KeyboardInterrupt):
            c.print("[dim]Cancelled.[/dim]")
            return

        # Find GGUF files
        try:
            files = list(api.list_repo_files(repo_id=selected_repo))
            gguf_files = [f for f in files if f.endswith(".gguf")]
        except Exception as e:
            c.print(f"[red]Could not list repo files: {e}[/red]")
            return

        if not gguf_files:
            c.print("[red]No .gguf files found in this repo.[/red]")
            return

        filename = gguf_files[0]
        if len(gguf_files) > 1:
            c.print("\n[bold]Available Quantizations:[/bold]")
            for i, f in enumerate(gguf_files):
                c.print(f"  [{i}] {f}")
            try:
                q_choice = input("Select quantization [0]: ").strip()
                if q_choice:
                    filename = gguf_files[int(q_choice)]
            except (ValueError, KeyboardInterrupt):
                pass

        model_tag = selected_repo.split("/")[-1].lower().replace(".", "-")
        self._download_status[model_tag] = "⬇ downloading..."

        def _do_download():
            try:
                c.print(f"\n[cyan]⬇ Downloading {filename}...[/cyan]")
                local_path = hf_hub_download(
                    repo_id=selected_repo,
                    filename=filename,
                    local_dir=self.local_models_dir,
                )
                self._download_status[model_tag] = "✅ done"

                c.print(f"[green]✅ Downloaded successfully! Use: /model {model_tag}[/green]")
                del self._download_status[model_tag]
            except Exception as e:
                self._download_status[model_tag] = f"✗ failed: {e}"
                c.print(f"[red]Download failed: {e}[/red]")

        # Allow passing background=False to block execution (e.g. for CLI `lmms pull`)
        import inspect
        frame = inspect.currentframe().f_back
        is_cli_pull = False
        while frame:
            if "cli.py" in frame.f_code.co_filename and frame.f_code.co_name == "handle_cli":
                is_cli_pull = True
                break
            frame = frame.f_back

        if is_cli_pull:
            _do_download()
        else:
            self._download_thread = threading.Thread(target=_do_download, daemon=True)
            self._download_thread.start()
            c.print(f"[green]Download started in background! Use /models to check progress.[/green]")

    # ──────────────────────────────────────────────
    # CLOUD CONNECTORS
    # ──────────────────────────────────────────────

    def _connectors_path(self):
        return os.path.expanduser("~/.lmms_connectors.json")

    def _load_connectors(self):
        path = self._connectors_path()
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def add_connector(self, name, api_key, base_url, api_type, model_name):
        connectors = self._load_connectors()
        connectors[name] = {
            "api_key": api_key.strip(),
            "base_url": base_url.strip(),
            "api_type": api_type.strip(),
            "model_name": model_name.strip(),
        }
        with open(self._connectors_path(), "w") as f:
            json.dump(connectors, f, indent=4)

    def remove_connector(self, name):
        connectors = self._load_connectors()
        if name in connectors:
            del connectors[name]
            with open(self._connectors_path(), "w") as f:
                json.dump(connectors, f, indent=4)
            return True
        return False

    def get_connector(self, name):
        return self._load_connectors().get(name)

    def list_connectors(self):
        return list(self._load_connectors().keys())

    # ──────────────────────────────────────────────
    # CLOUD CHAT  (actually calls the API!)
    # ──────────────────────────────────────────────

    def cloud_chat(self, connector_name: str, messages: list, stream: bool = False):
        """Actually call a cloud API connector. Returns response text."""
        connector = self.get_connector(connector_name)
        if not connector:
            return f"Connector '{connector_name}' not found."

        api_type = connector.get("api_type", "openai").lower()
        api_key = connector["api_key"]
        base_url = connector["base_url"]
        model_name = connector["model_name"]

        headers = {"Content-Type": "application/json"}

        if api_type == "anthropic":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
            # Convert messages — extract system
            system = ""
            chat_msgs = []
            for m in messages:
                if m["role"] == "system":
                    system = m["content"]
                else:
                    chat_msgs.append(m)
            payload = {
                "model": model_name,
                "max_tokens": 2048,
                "system": system,
                "messages": chat_msgs,
            }
            url = base_url.rstrip("/") + "/v1/messages"
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=60)
                r.raise_for_status()
                data = r.json()
                return data.get("content", [{}])[0].get("text", "")
            except Exception as e:
                return f"Anthropic API error: {e}"

        else:  # openai-compatible
            headers["Authorization"] = f"Bearer {api_key}"
            payload = {"model": model_name, "messages": messages, "max_tokens": 2048}
            url = base_url.rstrip("/") + "/v1/chat/completions"
            try:
                r = requests.post(url, headers=headers, json=payload, timeout=60)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                return f"OpenAI API error: {e}"

    # ──────────────────────────────────────────────
    # DOCTOR CHECK
    # ──────────────────────────────────────────────

    def doctor_check(self):
        """Returns list of (feature, status, detail) tuples for --doctor."""
        results = []

        # LMMS Engine
        if self.is_engine_running():
            models = self.list_available()
            results.append(("LMMS Engine", "✅ running", f"{len(models)} models available"))
        else:
            results.append(("LMMS Engine", "❌ offline", "Start: lmms server"))

        # Playwright
        try:
            from playwright.sync_api import sync_playwright
            results.append(("Playwright/Browser", "✅ installed", ""))
        except ImportError:
            results.append(("Playwright/Browser", "❌ missing", "pip install playwright && playwright install"))

        # AirLLM
        try:
            import airllm
            results.append(("AirLLM", "✅ installed", "70B+ models via disk"))
        except ImportError:
            results.append(("AirLLM", "❌ missing", "pip install airllm"))

        # HuggingFace Hub
        try:
            import huggingface_hub
            results.append(("HuggingFace Hub", "✅ installed", ""))
        except ImportError:
            results.append(("HuggingFace Hub", "❌ missing", "pip install huggingface_hub"))

        # Transformers
        try:
            import transformers
            results.append(("Transformers", "✅ installed", f"v{transformers.__version__}"))
        except ImportError:
            results.append(("Transformers", "❌ missing", "pip install transformers"))

        # Rich
        try:
            import rich
            results.append(("Rich UI", "✅ installed", f"v{rich.__version__}"))
        except ImportError:
            results.append(("Rich UI", "❌ missing", "pip install rich"))

        # VS Code
        try:
            r = subprocess.run(["code", "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                ver = r.stdout.strip().split("\n")[0]
                results.append(("VS Code", "✅ installed", f"v{ver}"))
            else:
                results.append(("VS Code", "❌ not found", "Install from code.visualstudio.com"))
        except Exception:
            results.append(("VS Code", "❌ not found", "Install from code.visualstudio.com"))

        # Continue.dev (VS Code extension)
        ext_dir = os.path.expanduser("~/.vscode/extensions")
        if os.path.exists(ext_dir):
            exts = os.listdir(ext_dir)
            has_continue = any("continue" in e.lower() for e in exts)
            if has_continue:
                results.append(("Continue.dev Ext", "✅ installed", ""))
            else:
                results.append(("Continue.dev Ext", "⚠ missing", "code --install-extension Continue.continue"))
        else:
            results.append(("Continue.dev Ext", "⚠ unknown", "VS Code not found"))

        # Cloud Connectors
        connectors = self._load_connectors()
        if connectors:
            names = ", ".join(connectors.keys())
            results.append(("Cloud Connectors", f"✅ {len(connectors)} connected", names))
        else:
            results.append(("Cloud Connectors", "○ none", "Use /connector to add"))

        # Canvas
        try:
            from lmms.canvas import get_canvas
            results.append(("Canvas", "✅ working", "Rich terminal renderer"))
        except Exception as e:
            results.append(("Canvas", "❌ broken", str(e)))

        # Sudo permissions
        try:
            r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=3)
            if r.returncode == 0:
                results.append(("Sudo (passwordless)", "✅ active", "Full system access"))
            else:
                results.append(("Sudo (passwordless)", "⚠ requires password", "Run: sudo LMMs for full power"))
        except Exception:
            results.append(("Sudo", "⚠ unknown", ""))

        return results
