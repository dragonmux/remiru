# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal, Const
from torii.build import Platform
from torii.lib.cdc import FFSynchronizer, PulseSynchronizer

__all__ = (
	'PDIInterface',
)

PDI_EMPTY_BYTE = Const(0xeb1, 9)
PDI_DELAY_BYTE = Const(0xdb1, 9)

class PDIInterface(Elaboratable):
	def __init__(self):
		# These signals represent the interface to the JTAG controller
		# JTAG data in here is data from the controller, while out is data to the controller.
		self.jtagDataIn = Signal(9)
		self.jtagDataOut = Signal(9)
		self.jtagNeedsResponse = Signal()
		self.jtagHasRequest = Signal()

		self.pdiDataIn = Signal(8)
		self.pdiDataOut = Signal(8)
		self.pdiBusy = Signal()
		self.pdiDone = Signal()
		self.pdiDoneAck = Signal()
		self.pdiNextReady = Signal()

	def elaborate(self, platform: Platform):
		m = Module()

		nextReady = Signal()
		useRequest = Signal()
		awaitingResponse = Signal()
		haveResponse = Signal()
		responseAck = Signal()
		pdiResponse = Signal(9)
		jtagResponse = Signal(9)

		responseAckSync = PulseSynchronizer(i_domain = 'jtag', o_domain = 'sync')

		# NB: The JTAG controller PDI signals are on the JTAG clock domain and
		# must be FFSynchronizer'd over to the main CPU clock domain for the
		# PDI controller, which exclusively sits on the main clock domain.
		m.submodules += [
			FFSynchronizer(self.pdiBusy, awaitingResponse, o_domain = 'jtag'),
			FFSynchronizer(self.pdiDone, haveResponse, o_domain = 'jtag'),
			responseAckSync,
			FFSynchronizer(nextReady, self.pdiNextReady, o_domain = 'sync'),
			FFSynchronizer(self.jtagDataIn, self.pdiDataIn, o_domain = 'sync'),
			FFSynchronizer(pdiResponse, jtagResponse, o_domain = 'jtag'),
		]

		m.d.comb += [
			# Copy the data to send into our pdiResponse
			pdiResponse[0:8].eq(self.pdiDataOut),
			# Compute its parity
			pdiResponse[8].eq(self.pdiDataOut.xor()),
			# Connect up the response acknowledgement signals thorugh their CDC sync
			responseAckSync.i.eq(responseAck),
			self.pdiDoneAck.eq(responseAckSync.o),
		]

		# If we have a response when the JTAG machinary asks for one, then we emit it, invalidating it.
		# Else, if we are awaiting a response then we respond with the PDI "Delay Byte" response till we
		# get one. Otherwise we must answer with the PDI "Empty Byte" response
		with m.If(self.jtagNeedsResponse):
			m.d.sync += useRequest.eq(~awaitingResponse)
			with m.If(haveResponse):
				m.d.comb += self.jtagDataOut.eq(jtagResponse)
				m.d.comb += responseAck.eq(1)
			with m.Elif(awaitingResponse):
				m.d.comb += self.jtagDataOut.eq(PDI_DELAY_BYTE)
			with m.Else():
				m.d.comb += self.jtagDataOut.eq(PDI_EMPTY_BYTE)

		# If awaitngResponse was low during the Capture-DR phase, then throw away the
		# request, otherwise forward it on to the PDI controller
		m.d.comb += nextReady.eq(useRequest & self.jtagHasRequest)

		return m
