# SPDX-License-Identifier: BSD-3-Clause
from ...framework import simCase
from torii import Elaboratable, Module, Signal
from torii.build import Platform
from torii.sim import Simulator, Settle, Delay

from ....debug.jtag import JTAGController, JTAGInstruction
from ....debug.pdi.interface import PDIInterface, PDI_BREAK_BYTE, PDI_DELAY_BYTE, PDI_EMPTY_BYTE

class Interface(Elaboratable):
	def __init__(self):
		# JTAG sim interface
		self.tck = Signal()
		self.tms = Signal()
		self.tdi = Signal()
		self.tdo = Signal()

		# PDI sim interface
		self.dataIn = Signal(9)
		self.dataOut = Signal(8)
		self.busy = Signal()
		self.parityError = Signal()
		self.done = Signal()
		self.doneAck = Signal()
		self.nextReady = Signal()

	def elaborate(self, platform: Platform):
		m = Module()
		m.submodules.jtag = jtag = JTAGController(jtagIDCode = 0x00000001)
		m.submodules.iface = iface = PDIInterface()

		# Connect the JTAG controller to the sim JTAG signals
		m.d.comb += [
			jtag.tck.eq(self.tck),
			jtag.tms.eq(self.tms),
			jtag.tdi.eq(self.tdi),
			self.tdo.eq(jtag.tdo),
		]

		# Connect the PDI JTAG interface signals to the JTAG controller
		m.d.comb += [
			iface.jtagDataIn.eq(jtag.pdiDataIn),
			jtag.pdiDataOut.eq(iface.jtagDataOut),
			iface.jtagHasRequest.eq(jtag.pdiHaveRequest),
			iface.jtagNeedsResponse.eq(jtag.pdiFetchResponse),
		]

		# Connect the PDI <=> JTAG interface up to the sim PDI signals
		m.d.comb += [
			self.dataIn.eq(iface.pdiDataIn),
			iface.pdiDataOut.eq(self.dataOut),
			iface.pdiBusy.eq(self.busy),
			iface.pdiParityError.eq(self.parityError),
			iface.pdiDone.eq(self.done),
			self.doneAck.eq(iface.pdiDoneAck),
			self.nextReady.eq(iface.pdiNextReady),
		]

		return m

@simCase(
	# Use a 12MHz clock for the sync domain
	domains = (('sync', 12e6),),
	dut = Interface()
)
def pdiInterface(sim: Simulator, dut: Interface):
	def domainSync():
		yield Settle()
		yield
		# Wait for the request signal to propergate through
		while not (yield dut.nextReady):
			yield Settle()
			yield
		# Go one more cycle
		yield dut.busy.eq(1)
		yield Settle()
		yield
		# Set up the response
		yield dut.busy.eq(0)
		yield dut.dataOut.eq(0x04)
		yield dut.done.eq(1)
		# Wait for the JTAG side to indicate it's done with the response
		while not (yield dut.doneAck):
			yield Settle()
			yield
		yield dut.done.eq(0)
		yield Settle()
		yield
		# Wait for the request signal to propergate through
		while not (yield dut.nextReady):
			yield Settle()
			yield
	yield domainSync, 'sync'

	# Cycle simulates a 20MHz clock on TCK for us
	def cycle():
		yield Settle()
		yield Delay(.5 / 20e6)
		yield dut.tck.eq(1)
		yield Settle()
		yield Delay(.5 / 20e6)
		yield dut.tck.eq(0)

	def softReset():
		yield dut.tms.eq(1)
		yield from cycle()
		yield from cycle()
		yield from cycle()
		yield from cycle()
		yield from cycle()
		yield dut.tms.eq(0)
		yield from cycle()

	def shiftIR():
		yield dut.tms.eq(1)
		yield from cycle()
		yield from cycle()
		yield dut.tms.eq(0)
		yield from cycle()
		yield from cycle()

	def shiftDR():
		yield dut.tms.eq(1)
		yield from cycle()
		yield dut.tms.eq(0)
		yield from cycle()
		yield from cycle()

	def returnToIdle():
		yield dut.tms.eq(1)
		yield from cycle()
		yield dut.tms.eq(0)
		yield from cycle()

	def transfer(*, dataIn: int, cycles: int) -> int:
		dataOut = 0
		for bit in range(cycles):
			# Set up the bit to send
			yield dut.tdi.eq((dataIn >> bit) & 1)
			# If this is the last bit, set go to the exit state
			yield dut.tms.eq(1 if bit == cycles - 1 else 0)
			yield Settle()
			yield Delay(.5 / 20e6)
			# Do the rising edge
			yield dut.tck.eq(1)
			yield Settle()
			# Grab the bit received
			dataOut |= (yield dut.tdo) << bit
			yield Delay(.5 / 20e6)
			# Do the falling edge
			yield dut.tck.eq(0)
		return dataOut

	def pdiTransfer(*, dataIn: int) -> int:
		yield from shiftDR()
		dataOut = yield from transfer(dataIn = dataIn, cycles = 9)
		yield from returnToIdle()
		return dataOut

	# This does the simulation on the an unclocked domain so we have control over the relationship
	# between the TMS and TDI signals to TCK (whether they're changing faling or rising edge, the
	# spacing between TCK edges, etc)
	def domainJTAG():
		# This ensures the controller is definitely reset and idle
		yield from softReset()
		# Wait a bit
		yield Delay(4 / 20e6)
		# Switch to the PDI instruction
		yield from shiftIR()
		yield from transfer(dataIn = JTAGInstruction.pdi, cycles = 4)
		yield from returnToIdle()
		# Wait a bit
		yield Delay(4 / 20e6)
		# Do an LDCS sequence for the PDI status register
		data = yield from pdiTransfer(dataIn = 0x180)
		assert data == PDI_EMPTY_BYTE.value
		data = yield from pdiTransfer(dataIn = 0x000)
		assert data == PDI_DELAY_BYTE.value
		data = yield from pdiTransfer(dataIn = 0x000)
		assert data == 0x104
		# Wait a bit
		yield Delay(4 / 20e6)
		yield from cycle()
		# Wait a cycle
		yield Delay(1 / 20e6)
	sim.add_process(domainJTAG)
