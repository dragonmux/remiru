# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module

from .debug import DebugController

__all__ = (
	'RemiruSoC',
)

class RemiruSoC(Elaboratable):
	def elaborate(self, platform):
		m = Module()
		m.submodules.debugController = debugController = DebugController()

		return m
