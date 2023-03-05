# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module

__all__ = (
	'RemiruSoC',
)

class RemiruSoC(Elaboratable):
	def elaborate(self, platform):
		m = Module()

		return m
