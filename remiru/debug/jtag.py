# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal, Cat, ClockDomain, ClockSignal
from torii.build import Platform
from enum import IntEnum

__all__ = (
	'JTAGController',
)

# The JTAG IR is 4 bits long and follows the same instruction allocation
# as a real AVR part to maintian compatibility with them
class JTAGInstruction(IntEnum):
	idCode = 0x3
	pdi = 0x7
	bypass = 0xf

class JTAGController(Elaboratable):
	def __init__(self, *, jtagIDCode: int):
		# These must be connected to the physical JTAG pin interface
		self.tck = Signal()
		self.tms = Signal()
		self.tdi = Signal()
		self.tdo = Signal()

		# The data interface to the PDI controller
		self.pdiDataIn = Signal(9)
		self.pdiDataOut = Signal(9)
		self.pdiHaveRequest = Signal()
		self.pdiFetchResponse = Signal()

		# Internal state for defining the JTAG ID code that will be emitted
		self._jtagIDCode = jtagIDCode

	def elaborate(self, platform: Platform):
		m = Module()

		# These represent the physical pins fed into this module
		tck = self.tck
		tms = self.tms
		tdi = self.tdi
		tdo = self.tdo

		# Define a clock domain derived from TCK
		m.domains.jtag = ClockDomain()
		m.d.comb += ClockSignal(domain = 'jtag').eq(tck)

		# Internal state registers for the various states of the TAP state machine
		captureDR = Signal()
		captureIR = Signal()
		shiftDR = Signal()
		shiftIR = Signal()
		updateDR = Signal()
		updateIR = Signal()

		# Special internal JTAG data registers
		bypass = Signal()
		idCode = Signal(32)
		pdiData = Signal(9)

		# Define the TAP-internal instruction register and its shift register
		insn = Signal(4, decoder = JTAGInstruction)
		insnShiftReg = Signal.like(insn)

		# PDI request/response registers
		pdiHaveRequest = Signal()

		# Ensure the update signals are kept low at all times other than when they're pulsed by the JTAG TAP
		m.d.comb += [
			captureDR.eq(0),
			captureIR.eq(0),
			updateDR.eq(0),
			updateIR.eq(0),
			self.pdiFetchResponse.eq(0),
			self.pdiHaveRequest.eq(0),
		]

		# Implement the Test Access Port (TAP) controller state machine per IEEE 1149.1 §6.1.1.1.a pg24
		with m.FSM(domain = 'jtag', name = 'tapFSM'):
			# This coresponds with the Test-Logic-Reset state for the TAP
			with m.State('RESET'):
				with m.If(~tms):
					m.d.jtag += [
						shiftDR.eq(0),
						shiftIR.eq(0),
						insn.eq(JTAGInstruction.idCode),
					]
					m.next = 'IDLE'
			# This coresponds with the Run-Test/Idle state for the TAP
			with m.State('IDLE'):
				with m.If(tms):
					m.next = 'SELECT-DR'

			# These states implement the data register chain of the TAP state machine
			with m.State('SELECT-DR'):
				with m.If(tms):
					m.next = 'SELECT-IR'
				with m.Else():
					m.next = 'CAPTURE-DR'
			with m.State('CAPTURE-DR'):
				with m.If(tms):
					m.next = 'EXIT1-DR'
				with m.Else():
					# Pulse captureDR in this cycle, so that shift-in/out can begin in the next
					m.d.comb += captureDR.eq(1)
					m.d.jtag += shiftDR.eq(1)
					m.next = 'SHIFT-DR'
			with m.State('SHIFT-DR'):
				with m.If(tms):
					m.d.jtag += shiftDR.eq(0)
					m.next = 'EXIT1-DR'
			with m.State('EXIT1-DR'):
				with m.If(tms):
					m.next = 'UPDATE-DR'
				with m.Else():
					m.next = 'PAUSE-DR'
			with m.State('PAUSE-DR'):
				with m.If(tms):
					m.next = 'EXIT2-DR'
			with m.State('EXIT2-DR'):
				with m.If(tms):
					m.next = 'UPDATE-DR'
				with m.Else():
					m.next = 'SHIFT-DR'
			with m.State('UPDATE-DR'):
				m.d.comb += updateDR.eq(1)
				with m.If(tms):
					m.next = 'SELECT-DR'
				with m.Else():
					m.next = 'IDLE'

			# These states implement the instruction register chain of the TAP state machine
			with m.State('SELECT-IR'):
				with m.If(tms):
					m.next = 'RESET'
				with m.Else():
					m.next = 'CAPTURE-IR'
			with m.State('CAPTURE-IR'):
				with m.If(tms):
					m.next = 'EXIT1-IR'
				with m.Else():
					# Pulse captureIR in this cycle, so that shift-in/out can begin in the next
					m.d.comb += captureIR.eq(1)
					m.d.jtag += shiftIR.eq(1)
					m.next = 'SHIFT-IR'
			with m.State('SHIFT-IR'):
				with m.If(tms):
					m.d.jtag += shiftIR.eq(0)
					m.next = 'EXIT1-IR'
			with m.State('EXIT1-IR'):
				with m.If(tms):
					m.next = 'UPDATE-IR'
				with m.Else():
					m.next = 'PAUSE-IR'
			with m.State('PAUSE-IR'):
				with m.If(tms):
					m.next = 'EXIT2-IR'
			with m.State('EXIT2-IR'):
				with m.If(tms):
					m.next = 'UPDATE-IR'
				with m.Else():
					m.next = 'SHIFT-IR'
			with m.State('UPDATE-IR'):
				m.d.comb += updateIR.eq(1)
				with m.If(tms):
					m.next = 'SELECT-DR'
				with m.Else():
					m.next = 'IDLE'

		# The capture, shift and update states for each of the IR and DR drive
		# the process of getting data in and putting data out from the TAP over
		# the JTAG pins, so hook up the data regsiters needed on various instructions.

		# This block defines how the IR shift register works
		with m.If(captureIR):
			m.d.jtag += insnShiftReg.eq(insn)
		with m.Elif(shiftIR):
			m.d.jtag += insnShiftReg.eq(Cat(insnShiftReg[1:4], tdi))
			m.d.jtag += tdo.eq(insnShiftReg[0])
		with m.Elif(updateIR):
			m.d.jtag += insn.eq(insnShiftReg)

		# This block defines how the DR shift registers work
		with m.If(captureDR):
			with m.Switch(insn):
				with m.Case(JTAGInstruction.idCode):
					m.d.jtag += idCode.eq(self._jtagIDCode)
				with m.Case(JTAGInstruction.pdi):
					m.d.comb += self.pdiFetchResponse.eq(1)
					m.d.jtag += pdiData.eq(self.pdiDataOut)
		with m.Elif(shiftDR):
			with m.Switch(insn):
				with m.Case(JTAGInstruction.idCode):
					m.d.jtag += [
						idCode.eq(Cat(idCode[1:32], tdi)),
						tdo.eq(idCode[0]),
					]
				with m.Case(JTAGInstruction.pdi):
					m.d.jtag += [
						pdiData.eq(Cat(pdiData[1:9], tdi)),
						tdo.eq(pdiData[0]),
					]
				with m.Case(JTAGInstruction.bypass):
					m.d.jtag += [
						bypass.eq(tdi),
						tdo.eq(bypass),
					]
		with m.Elif(updateDR):
			with m.Switch(insn):
				with m.Case(JTAGInstruction.pdi):
					m.d.jtag += [
						self.pdiDataIn.eq(pdiData),
						pdiHaveRequest.eq(1),
					]

		# This generates the have request pulse one cycle later so self.pdiDataIn is valid when it fires.
		with m.If(pdiHaveRequest):
			m.d.comb += self.pdiHaveRequest.eq(1)
			m.d.jtag += pdiHaveRequest.eq(0)

		return m
