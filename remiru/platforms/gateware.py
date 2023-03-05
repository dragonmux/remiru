from torii.platform.vendor.lattice_ice40 import LatticeICE40Platform
from torii.build import Resource, Subsignal, Pins, Clock, Attrs

__all__ = (
	'RemiruSoCGatewarePlatform',
)

class RemiruSoCGatewarePlatform(LatticeICE40Platform):
	device = 'iCE40HX8K'
	package = 'BG121'
	toolchain = 'IceStorm'

	default_clk = 'sys_clk'

	resources = [
		Resource(
			'sys_clk', 0,
			Pins('B6', dir = 'i', assert_width = 1),
			Clock(12e6),
			Attrs(GLOBAL = True, IO_STANDARD = 'SB_LVCMOS')
		),
	]

	connectors = []

	def build(self, elaboratable, name = 'top', build_dir = 'build', do_build = True,
		program_opts = None, do_program = False, **kwargs):
		super().build(
			elaboratable, name, build_dir, do_build, program_opts, do_program,
			synth_opts = '-abc9', nextpnr_opts = '--tmg-ripup --seed=0',
			**kwargs
		)
