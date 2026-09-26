import shutil
import os
from pathlib import Path

source = Path("D:/Học tập kì 1/Học máy nâng cao Nguyễn Đình Quý/evolving-ai-kg/backups/legacy_pipeline_v1_backup/data/stage_4_4_runs")
dest = Path("data/stage_4_4_runs")

if not dest.exists():
    dest.mkdir(parents=True)

for item in source.iterdir():
    if item.is_dir():
        shutil.copytree(item, dest / item.name, dirs_exist_ok=True)
    else:
        shutil.copy2(item, dest / item.name)

print("Copy completed successfully.")
