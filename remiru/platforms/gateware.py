# SPDX-License-Identifier: BSD-3-Clause
from torii_boards.lattice.icebreaker import ICEBreakerPlatform
from torii.platform.resources.interface import JTAGResource
from torii.build import Resource, Subsignal, Pins, Clock, Attrs

__all__ = (
	'RemiruSoCGatewarePlatform',
)

class RemiruSoCGatewarePlatform(ICEBreakerPlatform):
	jtagIDCode = 0x00000001

	resources = ICEBreakerPlatform.resources + [
		JTAGResource(
			'jtag', 0,
			tck = '7',
			tms = '8',
			tdi = '9',
			tdo = '10',
			conn = ('pmod', 0)
		),
	]

	def build(self, elaboratable, name = 'top', build_dir = 'build', do_build = True,
		program_opts = None, do_program = False, **kwargs):
		super().build(
			elaboratable, name, build_dir, do_build, program_opts, do_program,
			synth_opts = '-abc9', nextpnr_opts = '--tmg-ripup --seed=0',
			**kwargs
		)
