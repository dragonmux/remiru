# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal
from torii.build import Platform
from enum import IntEnum

__all__ = (
	'PDIController',
)

class PDIOpcodes(IntEnum):
	(
		LDS, LD, STS, ST,
		LDCS, REPEAT, STCS, KEY,
	) = range(8)

	IDLE = 0xf

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

		opcode = Signal(PDIOpcodes)
		args = Signal(4)
		readCount = Signal(32)
		writeCount = Signal(32)

		# This FSM implements handling getting data into and out of the PDI controller
		with m.FSM(name = 'pdiFSM'):
			with m.State('RESET'):
				# When requested, quick-reset the state machine
				m.d.sync += [
					opcode.eq(PDIOpcodes.IDLE),
					self.parityError.eq(0),
					readCount.eq(0),
					writeCount.eq(0),
				]
				m.next = 'IDLE'

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
				with m.Elif(opcode == PDIOpcodes.IDLE):
					m.next = 'DECODE-INSN'
				with m.Elif(writeCount != 0):
					m.next = 'HANDLE-WRITE'
				with m.Else():
					m.next = 'HANDLE-READ'

			with m.State('DECODE-INSN'):
				pass

			with m.State('HANDLE-READ'):
				pass

			with m.State('HANDLE-WRITE'):
				pass

		return m
