# SPDX-License-Identifier: BSD-3-Clause
from torii import Elaboratable, Module
from torii.build import Platform

from .jtag import JTAGController
from .pdi.interface import PDIInterface
from .pdi.controller import PDIController

__all__ = (
	'DebugController',
)

# The PDI controller defines a special debug bus through which access to
# all peripherals etc is possible but gated behind the CPU status (running/paused)
# and whether the PDI controller's debug controller has been enabled
# and whether the PDI NVM controller has been enabled

class DebugController(Elaboratable):
	def elaborate(self, platform: Platform):
		m = Module()
		# Instantiate the PDI controller, interface and JTAG controller
		m.submodules.jtag = jtagController = JTAGController(jtagIDCode = platform.jtagIDCode)
		m.submodules.iface = pdiInterface = PDIInterface()
		m.submodules.pdi = pdiController = PDIController()

		# Connect the JTAG controller to the physical JTAG pins
		jtag = platform.request('jtag')
		m.d.comb += [
			jtagController.tck.eq(jtag.tck.i),
			jtagController.tms.eq(jtag.tms.i),
			jtagController.tdi.eq(jtag.tdi.i),
			jtag.tdo.o.eq(jtagController.tdo),
			jtag.tdo.oe.eq(1),
		]

		# Connect the PDI JTAG interface signals to the JTAG controller
		m.d.comb += [
			pdiInterface.jtagDataIn.eq(jtagController.pdiDataIn),
			jtagController.pdiDataOut.eq(pdiInterface.jtagDataOut),
			pdiInterface.jtagHasRequest.eq(jtagController.pdiHaveRequest),
			pdiInterface.jtagNeedsResponse.eq(jtagController.pdiFetchResponse),
		]

		# Connect the PDI <=> JTAG interface up to the PDI controller
		m.d.comb += [
			pdiController.dataIn.eq(pdiInterface.pdiDataIn),
			pdiInterface.pdiDataOut.eq(pdiController.dataOut),
			pdiInterface.pdiBusy.eq(pdiController.busy),
			pdiInterface.pdiParityError.eq(pdiController.parityError),
			pdiInterface.pdiDone.eq(pdiController.done),
			pdiController.doneAck.eq(pdiInterface.pdiDoneAck),
			pdiController.nextReady.eq(pdiInterface.pdiNextReady),
		]

		return m
