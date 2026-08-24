import os
import re
import signal
import subprocess
import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR / "backend"
ENV_PATH = BACKEND_DIR / ".env"
RUNTIME_PORT_PATH = PACKAGE_DIR / "backend-port.js"
WEB_PORT = int(os.environ.get("NOVELFORGE_WEB_PORT", "5173"))


def read_backend_port() -> int:
    if not ENV_PATH.is_file():
        return 54321
    content = ENV_PATH.read_text(encoding="utf-8")
    match = re.search(
        r'^\s*(?:export\s+)?APP_PORT\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^#]*?))(?:\s+#.*)?\s*$',
        content,
        re.MULTILINE,
    )
    value = (match.group(1) or match.group(2) or match.group(3) or "54321").strip() if match else "54321"
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError(f"APP_PORT in {ENV_PATH} must be an integer between 1 and 65535")
    return port


def main() -> None:
    backend_executable = BACKEND_DIR / ("NovelForgeBackend.exe" if sys.platform == "win32" else "NovelForgeBackend")
    if not backend_executable.is_file():
        raise FileNotFoundError(f"Backend executable not found: {backend_executable}")

    backend_port = read_backend_port()
    RUNTIME_PORT_PATH.write_text(
        f"globalThis.__NOVELFORGE_BACKEND_PORT__ = {backend_port};\n",
        encoding="utf-8",
    )

    backend_process = subprocess.Popen([str(backend_executable)], cwd=BACKEND_DIR)
    server_process = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(WEB_PORT), "--directory", str(PACKAGE_DIR)],
        cwd=PACKAGE_DIR,
    )

    def shutdown(*_args) -> None:
        for process in (backend_process, server_process):
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    print(f"NovelForge Web: http://127.0.0.1:{WEB_PORT}")
    print(f"Backend: http://127.0.0.1:{backend_port}")
    try:
        backend_process.wait()
    finally:
        shutdown()
        server_process.wait()


if __name__ == "__main__":
    main()
