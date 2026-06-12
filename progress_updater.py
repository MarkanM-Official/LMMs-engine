import os
import time
import json
import re

log_file = "/home/kali/.gemini/antigravity-ide/brain/8735fae9-12d3-485d-89b0-65857b0cf7ab/.system_generated/tasks/task-9246.log"
json_file = "/home/kali/.lmms/logs/downloads.json"

pattern = re.compile(r"(\d+)%\|.*?\| ([0-9.]+.*?/[0-9.]+.*?G) \[")

def tail_file(file_path):
    with open(file_path, 'r') as f:
        f.seek(0, 2)
        buffer = ""
        while True:
            chunk = f.read(1024)
            if not chunk:
                time.sleep(1)
                continue
            buffer += chunk
            parts = buffer.split('\r')
            if len(parts) > 1:
                for part in parts[:-1]:
                    yield part
                buffer = parts[-1]
            if '\n' in buffer:
                parts = buffer.split('\n')
                for part in parts[:-1]:
                    yield part
                buffer = parts[-1]

for line in tail_file(log_file):
    match = pattern.search(line)
    if match:
        pct = match.group(1)
        size = match.group(2)
        
        try:
            with open(json_file, "r") as f:
                d = json.load(f)
            
            updated = False
            for k, v in d.items():
                if "downloading" in v.get("status", "").lower():
                    d[k]["status"] = f"Downloading... {pct}% ({size})"
                    updated = True
            
            if updated:
                with open(json_file, "w") as f:
                    json.dump(d, f)
        except Exception as e:
            pass
