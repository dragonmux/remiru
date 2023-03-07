# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal, Cat
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
		readCount = Signal(4) # Counter for the number of bytes to read from the PDI interface
		writeCount = Signal(4) # Counter for the number of bytes to write to the PDI interface
		repCount = Signal(32) # Counter for the number of times the current instruction should be repeated
		updateCounts = Signal()
		updateRepeat = Signal()
		newCommand = Signal()

		m.d.comb += [
			updateCounts.eq(0),
			updateRepeat.eq(0),
		]

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
					# Unmark the controller as busy so we can get the next byte
					m.d.sync += self.busy.eq(0)
					m.next = 'HANDLE-READ'

				# If we didn't get a parity error, copy the data into the internal data register
				with m.If(~self.parityError):
					m.d.sync += data.eq(self.dataIn[0:8])

			with m.State('DECODE-INSN'):
				# Unpack the instruction into the internal instruction registers
				m.d.sync += [
					opcode.eq(data[5:8]),
					args.eq(data[0:4]),
					newCommand.eq(1),
				]
				m.d.comb += updateCounts.eq(1)
				m.next = 'IDLE'

			with m.State('HANDLE-READ'):
				with m.If(opcode == PDIOpcodes.REPEAT):
					m.d.comb += updateRepeat.eq(1)

			with m.State('HANDLE-WRITE'):
				pass

		sizeA = Signal(3)
		sizeB = Signal(3)
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
					# If we're asked to update counts and the IDLE opcode is selected,
					# clear the repeat counter and be done
					with m.Case(PDIOpcodes.IDLE):
						m.d.sync += repCount.eq(0)
						m.next = 'IDLE'
					# The next 4 cases handle the PDI debug bus load/store instructions
					with m.Case(PDIOpcodes.LDS):
						# LDS instructions specify how many bytes to read in sizeA
						# and how many bytes to write in sizeB
						m.d.sync += [
							writeCount.eq(sizeB),
							readCount.eq(sizeA),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.LD):
						# LD instructions specify how many bytes to write in sizeB
						# the instruction does not read any bytes
						m.d.sync += [
							writeCount.eq(sizeB),
							readCount.eq(0),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.STS):
						# STS instructions specify how many bytes to read in sizeA + sizeB
						# the instruction does not write any bytes
						m.d.sync += [
							writeCount.eq(0),
							readCount.eq(sizeA + sizeB),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.ST):
						# ST instructions specify how many bytes to read in sizeB
						# the instruction does not write any bytes
						m.d.sync += [
							writeCount.eq(0),
							readCount.eq(sizeB),
						]
						m.next = 'HANDLE-REPEAT'
					# The next 2 cases handle the PDI controller register load/store instructions
					with m.Case(PDIOpcodes.LDCS):
						# LDCS instructions only write a single byte and never read any bytes
						m.d.sync += [
							writeCount.eq(1),
							readCount.eq(0),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.STCS):
						# STCS instructions only read a single byte and never write any bytes
						m.d.sync += [
							writeCount.eq(0),
							readCount.eq(1),
						]
						m.next = 'HANDLE-REPEAT'
					# The repeat instruction is a special-case and must ignore the repeat counter
					with m.Case(PDIOpcodes.REPEAT):
						# REPEAT instructions specify how many bytes to read in sizeB
						# the instruction does not write any bytes
						m.d.sync += [
							writeCount.eq(0),
							readCount.eq(sizeB),
						]
						m.next = 'CAPTURE-REPEAT'
					# The key instruction is a special-case and must clear the repeat counter
					with m.Case(PDIOpcodes.KEY):
						# KEY instructions imply 8 bytes to read and never write any bytes
						m.d.sync += [
							writeCount.eq(0),
							readCount.eq(8),
							repCount.eq(0),
						]
						m.next = 'IDLE'

			with m.State('HANDLE-REPEAT'):
				# If a repeat count is in play, then we need to decrement it now the instruction
				# is set up for new execution
				with m.If((repCount != 0) & ~newCommand):
					m.d.sync += repCount.eq(repCount - 1)
				m.next = 'IDLE'

			with m.State('CAPTURE-REPEAT'):
				# Each time the control state machine indicates it got another byte for the repeat count,
				# shift that into the bottom of the repeatData register until we satisfy the read count
				with m.If(updateRepeat):
					m.d.sync += repeatData.eq(Cat(data, repeatData[0:24]))
					with m.If(readCount == 1):
						m.next = 'UPDATE-REPEAT'
			with m.State('UPDATE-REPEAT'):
				# Depending on how many bytes were indicated for the repeat count, load the repeat counter
				# appropriately, fixing the byte order (repeatData is loaded "backwards")
				with m.Switch(args[0:2]):
					with m.Case(0):
						m.d.sync += repCount.eq(Cat(repeatData[0:8]))
					with m.Case(1):
						m.d.sync += repCount.eq(Cat(repeatData[8:16], repeatData[0:8]))
					with m.Case(2):
						m.d.sync += repCount.eq(Cat(repeatData[16:24], repeatData[8:16], repeatData[0:8]))
					with m.Case(3):
						m.d.sync += repCount.eq(Cat(repeatData[24:32],
							repeatData[16:24], repeatData[8:16], repeatData[0:8]))
				m.next = 'IDLE'

		return m
