# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module, Signal, Const
from torii.build import Platform
from torii.lib.cdc import FFSynchronizer
from ...cdc import PulseSynchroniser

__all__ = (
	'PDIInterface',
)

PDI_BREAK_BYTE = Const(0x1bb, 9)
PDI_DELAY_BYTE = Const(0x1db, 9)
PDI_EMPTY_BYTE = Const(0x1eb, 9)

class PDIInterface(Elaboratable):
	def __init__(self):
		# These signals represent the interface to the JTAG controller
		# JTAG data in here is data from the controller, while out is data to the controller.
		self.jtagDataIn = Signal(9)
		self.jtagDataOut = Signal(9)
		self.jtagNeedsResponse = Signal()
		self.jtagHasRequest = Signal()

		self.pdiDataIn = Signal(9)
		self.pdiDataOut = Signal(8)
		self.pdiBusy = Signal()
		self.pdiParityError = Signal()
		self.pdiDone = Signal()
		self.pdiDoneAck = Signal()
		self.pdiNextReady = Signal()

	def elaborate(self, platform: Platform):
		m = Module()

		nextReady = Signal()
		useRequest = Signal()
		awaitingResponse = Signal()
		awaitingReg = Signal()
		busy = Signal()
		parityError = Signal()
		haveResponse = Signal()
		responseAck = Signal()
		pdiResponse = Signal(9)
		jtagResponse = Signal(9)

		responseAckSync = PulseSynchroniser(iDomain = 'jtag', oDomain = 'sync')
		nextReadySync = PulseSynchroniser(iDomain = 'jtag', oDomain = 'sync')

		# NB: The JTAG controller PDI signals are on the JTAG clock domain and
		# must be FFSynchronizer'd over to the main CPU clock domain for the
		# PDI controller, which exclusively sits on the main clock domain.
		m.submodules += [
			FFSynchronizer(self.pdiBusy, awaitingResponse, o_domain = 'jtag'),
			FFSynchronizer(self.pdiParityError, parityError, o_domain = 'jtag'),
			FFSynchronizer(self.pdiDone, haveResponse, o_domain = 'jtag'),
			responseAckSync,
			nextReadySync,
			FFSynchronizer(self.jtagDataIn, self.pdiDataIn, o_domain = 'sync'),
			FFSynchronizer(pdiResponse, jtagResponse, o_domain = 'jtag'),
		]

		m.d.comb += [
			# Copy the data to send into our pdiResponse
			pdiResponse[0:8].eq(self.pdiDataOut),
			# Compute its parity
			pdiResponse[8].eq(self.pdiDataOut.xor()),
			# Connect up the response acknowledgement signals through their CDC sync
			responseAckSync.i.eq(responseAck),
			self.pdiDoneAck.eq(responseAckSync.o),
			# Connect up the next ready signals through their CDC sync
			nextReadySync.i.eq(nextReady),
			self.pdiNextReady.eq(nextReadySync.o),
		]

		# If we have a request come in to use, immediately mark the PDI controller busy
		with m.If(nextReady):
			m.d.jtag += busy.eq(1)
		# If we just got done waiting for a response, unmark the controller busy
		with m.Elif(haveResponse | (awaitingReg & ~awaitingResponse)):
			m.d.jtag += busy.eq(0)
		# Register awaitingResponse so we can detect the falling edge
		m.d.jtag += awaitingReg.eq(awaitingResponse)

		# If we have a response when the JTAG machinary asks for one, then we emit it, invalidating it.
		# Else, if we are awaiting a response then we respond with the PDI "Delay Byte" response till we
		# get one. Otherwise we must answer with the PDI "Empty Byte" response.
		# If during reception the PDI controller sees invalid parity for the previous request,
		# then a PDI "Break Byte" will be generated instead indicating the parity error.
		with m.If(self.jtagNeedsResponse):
			m.d.jtag += useRequest.eq(~awaitingResponse)
			with m.If(parityError):
				m.d.comb += self.jtagDataOut.eq(PDI_BREAK_BYTE)
			with m.Elif(busy):
				m.d.comb += self.jtagDataOut.eq(PDI_DELAY_BYTE)
			with m.Elif(haveResponse):
				m.d.comb += [
					self.jtagDataOut.eq(jtagResponse),
					responseAck.eq(1),
				]
			with m.Else():
				m.d.comb += self.jtagDataOut.eq(PDI_EMPTY_BYTE)

		# If awaitngResponse was low during the Capture-DR phase, then throw away the
		# request, otherwise forward it on to the PDI controller
		m.d.comb += nextReady.eq(useRequest & self.jtagHasRequest)

		return m
