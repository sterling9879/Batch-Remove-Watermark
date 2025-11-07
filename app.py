from __future__ import annotations

import os

from batch_ui import build_interface


def main() -> None:
    api_key_from_env = os.getenv("WAVESPEED_API_KEY")
    iface = build_interface(default_api_key=api_key_from_env)
    if not api_key_from_env:
        print("Defina a variável de ambiente WAVESPEED_API_KEY ou informe pela interface.")
    iface.launch(server_name="0.0.0.0", server_port=7860)


if __name__ == "__main__":
    main()
