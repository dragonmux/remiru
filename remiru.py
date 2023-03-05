#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause

from sys import argv, path, exit
from pathlib import Path

gatewarePath = Path(argv[0]).resolve().parent
if (gatewarePath / 'remiru').is_dir():
	path.insert(0, str(gatewarePath))
else:
	raise ImportError('Cannot find the project remiru gateware')

from remiru import cli
if __name__ == '__main__':
	exit(cli())
