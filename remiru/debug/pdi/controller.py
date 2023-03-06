# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal
from torii.build import Platform

__all__ = (
	'PDIController',
)

class PDIController(Elaboratable):
	def __init__(self):
		self.dataIn = Signal(9)
		self.dataOut = Signal(8)
		self.busy = Signal()
		self.parityError = Signal()
		self.done = Signal()
		self.doneAck = Signal()
		self.nextReady = Signal()

	def elaborate(self, platform: Platform):
		m = Module()

		parity = self.dataIn[0:8].xor()

		# This FSM implements handling getting data into and out of the PDI controller
		with m.FSM(name = 'pdiFSM'):
			with m.State('IDLE'):
				# If the interface signals a new byte is ready, parity check it and then go into the instruction engine
				with m.If(self.nextReady):
					m.next = 'PARITY-CHECK'

			with m.State('PARITY-CHECK'):
				# With the parity computed, set up the parity error signal and mark us busy
				m.d.sync += [
					self.parityError.eq(parity != self.dataIn[8]),
					self.busy.eq(1),
				]
				# Then transition into the dispatcher (this will abort if a parity error is detected,
				# and will determine what this byte means to the current PDI state otherwise)
				m.next = 'DISPATCH-BYTE'

			with m.State('DISPATCH-BYTE'):
				with m.If(self.parityError):
					m.d.sync += self.busy.eq(0)
					m.next = 'IDLE'

		return m
