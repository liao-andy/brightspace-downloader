#!/usr/bin/env python3
"""Convenience launcher: `python run.py` starts the Brightspace Downloader app."""

from brightspace_downloader.app import main

if __name__ == "__main__":
    raise SystemExit(main())
