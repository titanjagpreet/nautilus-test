"""``python -m strategy_lab.data`` — run the data pipeline and print the quality report."""

from __future__ import annotations

import logging

from strategy_lab.data.pipeline import run


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(run())


if __name__ == "__main__":
    main()
