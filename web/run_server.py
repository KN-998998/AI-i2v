# -*- coding: utf-8 -*-
"""Start Uvicorn after enabling Windows console UTF-8 and ANSI support."""
from colorama import just_fix_windows_console

from web.core.settings import APP_HOST, APP_PORT, APP_RELOAD


def main() -> None:
    just_fix_windows_console()

    import uvicorn

    uvicorn.run(
        "web.app:app",
        host=APP_HOST,
        port=APP_PORT,
        reload=APP_RELOAD,
        use_colors=True,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
