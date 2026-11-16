from datetime import datetime

from dependency_support import data_root


def error(message):
    try:
        now = datetime.now()
        folder = data_root() / "logs"
        folder.mkdir(parents=True, exist_ok=True)

        with open(folder / f"hooks-{now:%Y-%m-%d}.log", "a", encoding="utf-8") as stream:
            stream.write(f"{now.isoformat(timespec='seconds')} {message}\n")
    except (OSError, ValueError):
        pass
