# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal, Cat, Array
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

		self.pdiRegs = Array((
			Signal(8, name = 'pdiStatus'), # r0
			Signal(8, name = 'pdiSysReset'), # r1
			Signal(8, name = 'pdiControl'), # r2
			Signal(8, name = 'pdiDebugStatus'), # r3
			Signal(8, name = 'pdiDebugControl'), # r4
		))

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
		updateComplete = Signal()
		newCommand = Signal()
		handleRead = Signal()
		handleWrite = Signal()
		writeComplete = Signal()

		m.d.comb += [
			updateCounts.eq(0),
			updateRepeat.eq(0),
			updateComplete.eq(0),
			writeComplete.eq(0),
		]

		# This FSM implements handling getting data into and out of the PDI controller
		with m.FSM(name = 'pdiFSM') as pdiFSM:
			m.d.comb += [
				handleRead.eq(pdiFSM.ongoing('HANDLE-READ')),
				handleWrite.eq(pdiFSM.ongoing('HANDLE-WRITE')),
			]

			with m.State('RESET'):
				# When requested, quick-reset the state machine
				m.d.sync += [
					opcode.eq(PDIOpcodes.IDLE),
					self.parityError.eq(0),
					readCount.eq(0),
					writeCount.eq(0),
					repCount.eq(0),
					self.busy.eq(0),
				]
				m.next = 'IDLE'

			with m.State('IDLE'):
				# If the interface signals a new byte is ready, parity check it and then go into the instruction engine
				with m.If(self.nextReady):
					m.next = 'PARITY-CHECK'

				# If the counter update indicates complete unmark the controller as being busy
				with m.If(updateComplete):
					m.d.sync += self.busy.eq(0)

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
				# Else if we must have more data to read, so dispatch to HANDLE-READ
				with m.Elif(readCount != 0):
					m.next = 'HANDLE-READ'
				# Else we have more data to write dispatch to HANDLE-WRITE
				with m.Else():
					m.next = 'HANDLE-WRITE'

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
				# Trigger an update of the read/write/repeat counters
				m.d.comb += updateCounts.eq(1)
				m.next = 'IDLE'

			with m.State('HANDLE-READ'):
				# Route the byte consumed from the JTAG-PDI bus to the appropriate part of the PDI controller
				m.d.sync += [
					readCount.eq(readCount - 1),
				]

				with m.If(opcode == PDIOpcodes.REPEAT):
					m.d.comb += updateRepeat.eq(1)
				m.next = 'UPDATE-STATE'

			with m.State('HANDLE-WRITE'):
				with m.If(writeComplete):
					# Route a byte from an appropriate part of the PDI controller to the JTAG-PDI bus
					m.d.sync += [
						writeCount.eq(writeCount - 1),
					]
					m.next = 'UPDATE-STATE'

			with m.State('UPDATE-STATE'):
				# If the read and write counters are exhausted, check if the data phase should repeat
				with m.If((writeCount == 0) & (readCount == 0)):
					# Trigger an update of the read/write/repeat counters on repeat
					with m.If(repCount != 0):
						m.d.sync += newCommand.eq(0)
						m.d.comb += updateCounts.eq(1)
					# We're done with the instruction, so put the PDI controller back in full idle
					with m.Else():
						m.d.sync += [
							opcode.eq(PDIOpcodes.IDLE),
							self.busy.eq(0),
						]
				# If we have no counter updates to do, reset the busy signal
				with m.Else():
					m.d.sync += self.busy.eq(0)
				# Wait for the next byte to be received
				m.next = 'IDLE'

		sizeA = Signal(3)
		sizeB = Signal(3)
		repeatData = Signal(32)

		m.d.comb += [
			sizeA.eq(args[2:4] + 1),
			sizeB.eq(args[0:2] + 1),
		]

		updateWasOngoing = Signal()

		with m.FSM(name = 'insnFSM') as insnFSM:
			# Generate a signal representing if we've been doing an update
			m.d.sync += updateWasOngoing.eq(~insnFSM.ongoing('IDLE'))
			# and then a strobe for when that update completes and we go back to idle
			m.d.comb += updateComplete.eq(insnFSM.ongoing('IDLE') & updateWasOngoing)

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
							readCount.eq(sizeA),
							writeCount.eq(sizeB),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.LD):
						# LD instructions specify how many bytes to write in sizeB
						# the instruction does not read any bytes
						m.d.sync += [
							readCount.eq(0),
							writeCount.eq(sizeB),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.STS):
						# STS instructions specify how many bytes to read in sizeA + sizeB
						# the instruction does not write any bytes
						m.d.sync += [
							readCount.eq(sizeA + sizeB),
							writeCount.eq(0),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.ST):
						# ST instructions specify how many bytes to read in sizeB
						# the instruction does not write any bytes
						m.d.sync += [
							readCount.eq(sizeB),
							writeCount.eq(0),
						]
						m.next = 'HANDLE-REPEAT'
					# The next 2 cases handle the PDI controller register load/store instructions
					with m.Case(PDIOpcodes.LDCS):
						# LDCS instructions only write a single byte and never read any bytes
						m.d.sync += [
							readCount.eq(0),
							writeCount.eq(1),
						]
						m.next = 'HANDLE-REPEAT'
					with m.Case(PDIOpcodes.STCS):
						# STCS instructions only read a single byte and never write any bytes
						m.d.sync += [
							readCount.eq(1),
							writeCount.eq(0),
						]
						m.next = 'HANDLE-REPEAT'
					# The repeat instruction is a special-case and must ignore the repeat counter
					with m.Case(PDIOpcodes.REPEAT):
						# REPEAT instructions specify how many bytes to read in sizeB
						# the instruction does not write any bytes
						m.d.sync += [
							readCount.eq(sizeB),
							writeCount.eq(0),
						]
						m.next = 'CAPTURE-REPEAT'
					# The key instruction is a special-case and must clear the repeat counter
					with m.Case(PDIOpcodes.KEY):
						# KEY instructions imply 8 bytes to read and never write any bytes
						m.d.sync += [
							readCount.eq(8),
							writeCount.eq(0),
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

		# This next block of logic handles dispatching reads and writes for various instructions
		# to the PDI correct components on the appropriate cycles
		with m.Switch(opcode):
			with m.Case(PDIOpcodes.LDCS):
				with m.If(handleWrite):
					m.d.sync += self.dataOut.eq(self.pdiRegs[args])
					m.d.comb += writeComplete.eq(1)
			with m.Case(PDIOpcodes.STCS):
				with m.If(handleRead):
					m.d.sync += self.pdiRegs[args].eq(data)

		# When the JTAG interface indicates it finished with the prepared data, clear done
		with m.If(self.doneAck):
			m.d.sync += self.done.eq(0)
		# If we indicate we're done setting up the data to write, set done
		with m.Elif(writeComplete):
			m.d.sync += self.done.eq(1)

		return m
