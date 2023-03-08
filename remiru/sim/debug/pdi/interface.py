# SPDX-License-Identifier: BSD-3-Clause
from ...framework import simCase
from torii.sim import Simulator, Settle

from ....debug.pdi.interface import PDIInterface, PDI_BREAK_BYTE, PDI_DELAY_BYTE, PDI_EMPTY_BYTE

@simCase(
	domains = (('sync', 25e6), ('jtag', 10e6)),
	dut = PDIInterface()
)
def pdiInterface(sim: Simulator, dut: PDIInterface):
	def domainJTAG():
		yield Settle()
		yield
		# When newly powered up/reset, the controller shouldn't have any responses ready and should
		# output the empty byte when JTAG requests a response
		yield dut.jtagNeedsResponse.eq(1)
		yield Settle()
		pdiData = yield dut.jtagDataOut
		assert pdiData == PDI_EMPTY_BYTE.value
		yield
		yield dut.jtagNeedsResponse.eq(0)
		yield Settle()
		yield
		# Pretend we instantly completed the JTAG transaction
		yield dut.jtagHasRequest.eq(1)
		yield dut.jtagDataIn.eq(0x180)
		yield Settle()
		yield
		yield dut.jtagHasRequest.eq(0)
		while not (yield dut.pdiDone):
			yield Settle()
			yield
		yield Settle()
		yield
		yield Settle()
		yield
		# Set up the next request
		yield dut.jtagNeedsResponse.eq(1)
		yield Settle()
		pdiData = yield dut.jtagDataOut
		# Check that the request that would be shifted out is a parity-correct copy of the PDI response
		assert pdiData == 0x104
		yield
		yield dut.jtagNeedsResponse.eq(0)
		yield Settle()
		yield
		# Pretend we instantly completed the JTAG transaction
		yield dut.jtagHasRequest.eq(1)
		# Intentionally cause a parity error so in the next transaction we can check for break byte
		yield dut.jtagDataIn.eq(0x100)
		yield Settle()
		yield
		yield dut.jtagHasRequest.eq(0)
		while (yield dut.pdiBusy):
			yield Settle()
			yield
		yield Settle()
		yield
		yield Settle()
		yield
		# Set up the next request
		yield dut.jtagNeedsResponse.eq(1)
		yield Settle()
		pdiData = yield dut.jtagDataOut
		assert pdiData == PDI_BREAK_BYTE.value
		yield
		yield dut.jtagNeedsResponse.eq(0)
		yield Settle()
		yield
		# Pretend we instantly completed the JTAG transaction
		yield dut.jtagHasRequest.eq(1)
		yield dut.jtagDataIn.eq(PDI_BREAK_BYTE)
		yield Settle()
		yield
		yield dut.jtagHasRequest.eq(0)
		# Wait for the PDI controller to go busy
		while not (yield dut.pdiBusy):
			yield Settle()
			yield
		yield Settle()
		yield
		yield Settle()
		yield
		# Set up the next request
		yield dut.jtagNeedsResponse.eq(1)
		yield Settle()
		pdiData = yield dut.jtagDataOut
		assert pdiData == PDI_DELAY_BYTE.value
		yield
		yield dut.jtagNeedsResponse.eq(0)
		yield Settle()
		yield
		# Pretend we instantly completed the JTAG transaction
		yield dut.jtagHasRequest.eq(1)
		yield dut.jtagDataIn.eq(PDI_BREAK_BYTE)
		yield Settle()
		yield
		yield dut.jtagHasRequest.eq(0)
		# Wait for the PDI controller to go idle
		while (yield dut.pdiBusy):
			yield Settle()
			yield
		yield Settle()
		yield
		yield Settle()
		yield
		# Set up the next request
		yield dut.jtagNeedsResponse.eq(1)
		yield Settle()
		pdiData = yield dut.jtagDataOut
		assert pdiData == 0
		yield
		yield dut.jtagNeedsResponse.eq(0)
		yield Settle()
		yield
		# Pretend we instantly completed the JTAG transaction
		yield dut.jtagHasRequest.eq(1)
		yield dut.jtagDataIn.eq(PDI_BREAK_BYTE)
		yield Settle()
		yield
		yield dut.jtagHasRequest.eq(0)
		yield Settle()
		yield
		yield Settle()
		yield
	yield domainJTAG, 'jtag'

	def domainSync():
		yield Settle()
		yield
		# Wait for the request signal to propergate through
		while not (yield dut.pdiNextReady):
			yield Settle()
			yield
		# Go one more cycle
		yield dut.pdiBusy.eq(1)
		yield Settle()
		yield
		# Set up the response
		yield dut.pdiBusy.eq(0)
		yield dut.pdiDataOut.eq(0x04)
		yield dut.pdiDone.eq(1)
		# Wait for the JTAG side to indicate it's done with the response
		while not (yield dut.pdiDoneAck):
			yield Settle()
			yield
		yield dut.pdiDone.eq(0)
		# Wait for the request signal to propergate through
		while not (yield dut.pdiNextReady):
			yield Settle()
			yield
		# Go one more cycle
		yield dut.pdiBusy.eq(1)
		yield Settle()
		yield
		# Set up the response
		yield dut.pdiBusy.eq(0)
		yield dut.pdiParityError.eq(1)
		# Wait for the JTAG side to be done with the response
		while not (yield dut.jtagHasRequest):
			yield Settle()
			yield
		# Wait for the request signal to propergate through
		while not (yield dut.pdiNextReady):
			yield Settle()
			yield
		# Go one more cycle
		yield dut.pdiBusy.eq(1)
		yield Settle()
		yield
		# Set up the response
		yield dut.pdiParityError.eq(0)
		yield Settle()
		yield
		# Wait for the JTAG side to be done with the response
		while not (yield dut.jtagHasRequest):
			yield Settle()
			yield
		for _ in range(4):
			yield Settle()
			yield
		# Set up the response
		yield dut.pdiBusy.eq(0)
		yield dut.pdiDataOut.eq(0)
		yield dut.pdiDone.eq(1)
		# Wait for the JTAG side to indicate it's done with the response
		while not (yield dut.pdiDoneAck):
			yield Settle()
			yield
		yield dut.pdiDone.eq(0)
		# Wait for the request signal to propergate through
		while not (yield dut.pdiNextReady):
			yield Settle()
			yield
		# Go one more cycle
		yield Settle()
		yield
	yield domainSync, 'sync'
