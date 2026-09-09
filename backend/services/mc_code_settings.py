import os


def mc_code_setting(suffix: str, default: str = "") -> str:
    """Prefer MC_CODE settings while accepting existing Azure CODEX settings."""
    return os.getenv(f"MC_CODE_{suffix}", os.getenv(f"CODEX_{suffix}", default))
