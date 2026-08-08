"""Console logging setup.

Named `logging_config` rather than `logging` so it is never mistaken for the
stdlib module.
"""

from __future__ import annotations

import logging
import logging.config

from app.core.config import Settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# uvicorn routes all of its lifecycle output - startup, shutdown, "Uvicorn
# running on..." - through a logger it named `uvicorn.error`, whatever the
# severity. Printed next to a level of INFO that reads like something failed.
DISPLAY_NAMES = {"uvicorn.error": "uvicorn"}


class LoggerNameFilter(logging.Filter):
    """Rewrite misleading logger names for display.

    Only the emitted record is touched; the logger itself keeps its real name,
    so level configuration and `LOG_UVICORN_ACCESS` are unaffected.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.name = DISPLAY_NAMES.get(record.name, record.name)
        return True


def setup_logging(settings: Settings) -> None:
    """Send all application logging to stdout.

    Safe to call repeatedly: `dictConfig` replaces handlers rather than
    appending. It is called again from the app's lifespan because uvicorn
    reconfigures logging after importing this module and would otherwise
    re-enable its own access log.
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {"format": LOG_FORMAT, "datefmt": DATE_FORMAT},
            },
            "filters": {
                "display_names": {"()": f"{__name__}.LoggerNameFilter"},
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "console",
                    "stream": "ext://sys.stdout",
                    "filters": ["display_names"],
                },
            },
            "root": {"level": settings.LOG_LEVEL, "handlers": ["console"]},
            "loggers": {
                # Route uvicorn's output through the same handler, and stop it
                # propagating to root so each line is printed once.
                **{
                    name: {
                        "level": settings.LOG_LEVEL,
                        "handlers": ["console"],
                        "propagate": False,
                    }
                    for name in ("uvicorn", "uvicorn.error")
                },
                # Silenced by default: RequestLoggingMiddleware already logs
                # every request, with a request id and a duration attached.
                "uvicorn.access": {
                    "level": settings.LOG_LEVEL if settings.LOG_UVICORN_ACCESS else "WARNING",
                    "handlers": ["console"],
                    "propagate": False,
                },
                # These log a line per HTTP call at INFO, duplicating our own
                # access log. Only surface them when something goes wrong.
                **{name: {"level": "WARNING"} for name in ("httpx", "httpcore")},
            },
        }
    )
