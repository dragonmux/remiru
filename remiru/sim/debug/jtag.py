# SPDX-License-Identifier: BSD-3-Clause
from ..framework import simCase
from torii.sim import Simulator, Settle, Delay

from ...debug.jtag import JTAGController, JTAGInstruction

@simCase(
	domains = (),
	dut = JTAGController(jtagIDCode = 0x12345678)
)
def basicJTAGOperations(sim: Simulator, dut: JTAGController):
	# Cycle simulates a 10MHz clock on TCK for us
	def cycle():
		yield Settle()
		yield Delay(.5 / 10e6)
		yield dut.tck.eq(1)
		yield Settle()
		yield Delay(.5 / 10e6)
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
			yield Delay(.5 / 10e6)
			# Do the rising edge
			yield dut.tck.eq(1)
			yield Settle()
			# Grab the bit received
			dataOut |= (yield dut.tdo) << bit
			yield Delay(.5 / 10e6)
			# Do the falling edge
			yield dut.tck.eq(0)
		return dataOut

	# This does the simulation on the an unclocked domain so we have control over the relationship
	# between the TMS and TDI signals to TCK (whether they're changing faling or rising edge, the
	# spacing between TCK edges, etc)
	def domainJTAG():
		# This ensures the controller is definitely reset and idle
		yield from softReset()
		# Wait a bit
		yield Delay(10 / 10e6)
		# Dump out the ID code
		yield from shiftDR()
		idCode = yield from transfer(dataIn = 0, cycles = 32)
		assert idCode == 0x12345678, f'JTAG ID code was {idCode:08x}, expecting 12345678'
		yield from returnToIdle()
		# Wait a bit
		yield Delay(4 / 10e6)
		# Switch to the bypass instruction and check the instruction shifted out matches the ID instruction
		yield from shiftIR()
		ir = yield from transfer(dataIn = JTAGInstruction.bypass, cycles = 4)
		assert ir == JTAGInstruction.idCode, f'JTAG IR was {ir:x}, expecting {JTAGInstruction.idCode:x}'
		yield from returnToIdle()
		# Wait a bit
		yield Delay(4 / 10e6)
		# Verify that the bypass register starts out 0 and results in a 1 bit delay
		yield from shiftDR()
		bypass = yield from transfer(dataIn = 0x5, cycles = 3)
		assert bypass == 0x2, f'Read {bypass:x} in BYPASS mode, expecting 2'
		yield from returnToIdle()
		# Wait a bit
		yield Delay(4 / 10e6)
		# Switch to the PDI instruction and check the instruction shifted out matches the bypass
		yield from shiftIR()
		ir = yield from transfer(dataIn = JTAGInstruction.pdi, cycles = 4)
		assert ir == JTAGInstruction.bypass, f'JTAG IR was {ir:x}, expecting {JTAGInstruction.bypass:x}'
		yield from returnToIdle()
		# Wait a bit
		yield Delay(4 / 10e6)
		# Set up a PDI empty byte response
		yield dut.pdiDataOut.eq(0x1eb)
		# Switch into PDI mode and shift in a test value of all 1's
		yield from shiftDR()
		pdi = yield from transfer(dataIn = 0x1ff, cycles = 9)
		assert pdi == 0x1eb, f'JTAG-PDI response was {pdi:03x}, was expecting 1eb'
		yield from returnToIdle()
		pdi = yield dut.pdiDataIn
		assert pdi == 0x1ff, f'Internal JTAG-PDI request value was {pdi:03x}, was expecting 1ff'
		# Set up an all 0 PDI response
		yield dut.pdiDataOut.eq(0x000)
		# Switch into PDI mode and shift in a test value to check and ensure nibble order
		yield from shiftDR()
		pdi = yield from transfer(dataIn = 0x012, cycles = 9)
		assert pdi == 0x000, f'JTAG-PDI response was {pdi:03x}, was expecting 000'
		yield from returnToIdle()
		pdi = yield dut.pdiDataIn
		assert pdi == 0x012, f'Internal JTAG-PDI request value was {pdi:03x}, was expecting 012'
		# Wait a cycle
		yield Delay(1 / 10e6)
	sim.add_process(domainJTAG)
	return ()
