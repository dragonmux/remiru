# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal, Const
from torii.build import Platform

__all__ = (
	'PDIInterface',
)

PDI_EMPTY_BYTE = Const(0xeb1, 9)
PDI_DELAY_BYTE = Const(0xdb1, 9)

class PDIInterface(Elaboratable):
	def __init__(self):
		# These signals represent the interface to the JTAG controller
		# JTAG data in here is data from the controller, while out is data to the controller.
		self.jtagDataIn = Signal(9)
		self.jtagDataOut = Signal(9)
		self.jtagNeedsResponse = Signal()
		self.jtagHasRequest = Signal()

		self.pdiDataIn = Signal(8)
		self.pdiDataOut = Signal(8)

	def elaborate(self, platform: Platform):
		m = Module()

		# The JTAG controller PDI signals are on the JTAG clock domain and
		# must be FFSynchronizer'd over to the main CPU clock domain for the
		# PDI controller, which exclusively sits on the main clock domain.

		haveResponse = Signal()
		awaitingResponse = Signal()
		pdiResponse = Signal(9)

		# If we have a response when the JTAG machinary asks for one, then we emit it, invalidating it.
		# Else, if we are awaiting a response then we respond with the PDI "Delay Byte" response till we
		# get one. Otherwise we must answer with the PDI "Empty Byte" response
		with m.If(self.jtagNeedsResponse):
			with m.If(haveResponse):
				m.d.comb += self.jtagDataOut.eq(pdiResponse)
				m.d.jtag += haveResponse.eq(0)
			with m.Elif(awaitingResponse):
				m.d.comb += self.jtagDataOut.eq(PDI_DELAY_BYTE)
			with m.Else():
				m.d.comb += self.jtagDataOut.eq(PDI_EMPTY_BYTE)

		return m
