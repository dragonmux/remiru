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

		data = Signal(8)
		opcode = Signal(PDIOpcodes)
		args = Signal(4)
		readCount = Signal(32)
		writeCount = Signal(32)
		repCount = Signal(32)
		updateCounts = Signal()

		# This FSM implements handling getting data into and out of the PDI controller
		with m.FSM(name = 'pdiFSM'):
			with m.State('RESET'):
				# When requested, quick-reset the state machine
				m.d.sync += [
					opcode.eq(PDIOpcodes.IDLE),
					self.parityError.eq(0),
					readCount.eq(0),
					writeCount.eq(0),
					repCount.eq(0),
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
				# Check if we've got a parity error and dispatch on it
				with m.If(self.parityError):
					m.d.sync += self.busy.eq(0)
					m.next = 'IDLE'
				# Else if we're in an idle state, treat the new byte as an opcode
				with m.Elif(opcode == PDIOpcodes.IDLE):
					m.next = 'DECODE-INSN'
				# Else if we have more data to write dispatch to HANDLE-WRITE
				with m.Elif(writeCount != 0):
					m.next = 'HANDLE-WRITE'
				# Else we must have more data to read, so dispatch to HANDLE-READ
				with m.Else():
					m.next = 'HANDLE-READ'

				# If we didn't get a parity error, copy the data into the internal data register
				with m.If(~self.parityError):
					m.d.sync += data.eq(self.dataIn[0:8])

			with m.State('DECODE-INSN'):
				# Unpack the instruction into the internal instruction registers
				m.d.sync += [
					opcode.eq(data[5:8]),
					args.eq(data[0:4]),
				]
				m.d.comb += updateCounts.eq(1)
				m.next = 'IDLE'

			with m.State('HANDLE-READ'):
				pass

			with m.State('HANDLE-WRITE'):
				pass

		sizeA = Signal(5)
		sizeB = Signal(5)
		repeatData = Signal(32)

		m.d.comb += [
			sizeA.eq(args[2:4] + 1),
			sizeB.eq(args[0:2] + 1),
		]

		with m.FSM(name = 'insnFSM'):
			with m.State('IDLE'):
				# If the main FSM asks us to update counts, then dispatch to the instruction decoder
				with m.If(updateCounts):
					m.next = 'DECODE'

			with m.State('DECODE'):
				# Decode based on the opcode
				with m.Switch(opcode):
					with m.Case(PDIOpcodes.IDLE):
						m.d.sync += repCount.eq(0)
						m.next = 'IDLE'

		return m
