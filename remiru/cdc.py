from torii import Elaboratable, Module, Signal
from torii.build import Platform
from torii.lib.cdc import FFSynchronizer, _check_stages as checkStages

__all__ = (
	'PulseSynchroniser',
)

class PulseSynchroniser(Elaboratable):
	'''A one-clock pulse on the input produces a one-clock pulse on the output.

	If the output clock is faster than the input clock, then the input may be safely asserted at
	100% duty cycle. Otherwise, if the clock ratio is ``n``:1, the input may be asserted at most
	once in every ``n`` input clocks, else pulses may be dropped. Other than this there is
	no constraint on the ratio of input and output clock frequency.

	Parameters
	----------
	iDomain : str
		Name of input clock domain.
	oDomain : str
		Name of output clock domain.
	stages : int, >=2
		Number of synchronization stages between input and output. The lowest safe number is 2,
		with higher numbers reducing MTBF further, at the cost of increased de-assertion latency.
	'''
	def __init__(self, iDomain: str, oDomain: str, *, stages: int = 2) -> None:
		checkStages(stages)

		# CDC interface
		self.i = Signal()
		self.o = Signal()

		# Internals
		self._iDomain = iDomain
		self._oDomain = oDomain
		self._stages = stages

	def elaborate(self, platform: Platform) -> Module:
		m = Module()
		domainIn = self._iDomain
		domainOut = self._oDomain

		# These signals track when a rising edge has been seen for CDC
		toggleIn = Signal()
		toggleInReg = Signal()
		toggleOut = Signal()
		toggleOutReg = Signal()

		# Synchronise the toggleIn signal over to the output clock domain
		m.submodules += [
			FFSynchronizer(toggleIn, toggleOut, o_domain = domainOut, stages = self._stages),
		]

		# Generate and register when a rising edge occurs
		m.d.comb += toggleIn.eq(toggleInReg ^ self.i)
		m.d[domainIn] += toggleInReg.eq(toggleIn)

		# Generate and register a pulse on the output clock domain in response
		m.d.comb += self.o.eq(toggleOut ^ toggleOutReg)
		m.d[domainOut] += toggleOutReg.eq(toggleOut)

		return m
