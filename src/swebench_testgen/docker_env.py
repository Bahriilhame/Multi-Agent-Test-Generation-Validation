"""Docker availability and bounded command entry points."""

import shutil
import subprocess


def docker_status() -> dict[str, object]:
    executable = shutil.which("docker")
    if not executable:
        return {"available": False, "reason": "docker executable not found"}
    result = subprocess.run([executable, "info", "--format", "{{.OSType}} {{.Architecture}}"],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        return {"available": False, "reason": result.stderr.strip() or "Docker daemon unavailable"}
    return {"available": True, "engine": result.stdout.strip()}

