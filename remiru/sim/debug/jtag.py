# SPDX-License-Identifier: BSD-3-Clause
from ..framework import simCase
from torii.sim import Simulator, Settle, Delay

from ...debug.jtag import JTAGController

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

	# This does the simulation on the sync domain so we have control over the relationship between the
	# TMS and TDI signals to TCK (whether they're changing faling or rising edge, the spacing between
	# TCK edges, etc)
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
		# Switch to the bypass state and check the instruction shifted out matches the ID instruction
		yield from shiftIR()
		ir = yield from transfer(dataIn = 0xf, cycles = 4)
		assert ir == 0x3, f'JTAG IR was {ir:x}, expecting 3'
		yield from returnToIdle()
		# Wait a bit
		yield Delay(4 / 10e6)
		# Verify that the bypass register starts out 0 and results in a 1 bit delay
		yield from shiftDR()
		bypass = yield from transfer(dataIn = 0x5, cycles = 3)
		assert bypass == 0x2, f'Read {bypass:x} in BYPASS mode, expecting 2'
		yield from returnToIdle()
		# Wait a cycle
		yield Delay(1 / 10e6)
	sim.add_process(domainJTAG)
	return ()
