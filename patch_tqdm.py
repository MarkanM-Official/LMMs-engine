import json
from huggingface_hub.utils import _tqdm
original_tqdm = _tqdm.tqdm

class DownloadTqdm(original_tqdm):
    def update(self, n=1):
        super().update(n)
        if hasattr(self, 'total') and self.total:
            pct = int((self.n / self.total) * 100)
            speed = getattr(self, 'format_dict', {}).get('rate', 0)
            if speed:
                speed_str = f"{speed / 1024 / 1024:.2f} MB/s"
            else:
                speed_str = ""
            
            # Update downloads.json
            try:
                import os
                f = os.path.expanduser("~/.lmms/logs/downloads.json")
                with open(f, "r") as file:
                    d = json.load(file)
                # Find the downloading one
                for k, v in d.items():
                    if v.get("status", "").startswith("downloading") or v.get("status", "").startswith("Downloading"):
                        d[k]["status"] = f"Downloading... {pct}% ({speed_str})"
                with open(f, "w") as file:
                    json.dump(d, file)
            except Exception as e:
                pass

_tqdm.tqdm = DownloadTqdm
print("Patched!")
