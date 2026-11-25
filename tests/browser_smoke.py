"""Executa o fluxo sintético num navegador, com FastAPI e armazenamento temporários."""

import socket
import subprocess
import tempfile
import threading
from pathlib import Path

import uvicorn

from backend.api import app
from backend.services import armazenamento
from tests.fixtures_wrf import dominio_sintetico


def main():
    with tempfile.TemporaryDirectory() as temporario:
        armazenamento.STORAGE_DIR = Path(temporario)
        dominio = Path(temporario) / "wrfinput_sintetico"
        dominio_sintetico(dominio)
        with socket.create_server(("127.0.0.1", 0)) as listener:
            porta = listener.getsockname()[1]
            servidor = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
            thread = threading.Thread(target=servidor.run, kwargs={"sockets": [listener]}, daemon=True)
            thread.start()
            try:
                subprocess.run(
                    ["node", str(Path(__file__).with_name("browser_smoke.cjs")),
                     f"http://127.0.0.1:{porta}", str(dominio)],
                    check=True, timeout=90,
                )
            finally:
                servidor.should_exit = True
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
