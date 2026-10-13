"""Shared HOLiNFORM root/config paths. Does not hard-code the root in business logic."""
from __future__ import annotations
import json
import os
from pathlib import Path


def root_path(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser()
    if os.environ.get('HOLINFORM_ROOT'):
        return Path(os.environ['HOLINFORM_ROOT']).expanduser()
    global_config = Path(os.environ.get('PROGRAMDATA', r'C:\ProgramData')) / 'HOLiNFORM' / 'global.json'
    try:
        configured = json.loads(global_config.read_text(encoding='utf-8')).get('root_path')
        if configured:
            return Path(configured)
    except (OSError, ValueError, TypeError):
        pass
    return Path(r'C:\HOLiNFORM') if os.name == 'nt' else Path.home() / 'HOLiNFORM'


def module_paths(root: Path):
    return {
        'db': root / 'data' / 'HOLiZEK' / 'holizek.sqlite3',
        'image_store': root / 'data' / 'HOLiZEK' / 'images',
        'image_import': root / 'import' / 'HOLiZEK',
        'config': root / 'config' / 'HOLiZEK' / 'ui.json',
        'log': root / 'logs' / 'HOLiZEK' / 'holizek.log',
    }
