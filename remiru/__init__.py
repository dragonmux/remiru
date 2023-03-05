# SPDX-License-Identifier: BSD-3-Clause
from .soc import RemiruSoC

__all__ = (
	'cli',
)

def build(buildAs: str):
	if buildAs == 'gateware':
		from .platforms import RemiruSoCGatewarePlatform
		platform = RemiruSoCGatewarePlatform()
	# elif buildAs == 'asic':
	# 	from .platforms import RimuruSoCASICPlatform
	# 	platform = RimuruSoCASICPlatform()
	platform.build(RemiruSoC(), name = 'remiruSoC')

def cli():
	from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

	parser = ArgumentParser(formatter_class = ArgumentDefaultsHelpFormatter,
		description = 'project remiru')
	actions = parser.add_subparsers(dest = 'action', required = True)

	buildAction = actions.add_parser('build', help = 'build the project remiru SoC gateware')
	actions.add_parser('sim', help = 'Simulate the gateware components')
	actions.add_parser('formal', help = 'Formally verify the gateware components')

	buildAction.add_argument('--as', dest = 'buildAs', action = 'store', required = True,
		choices = ('gateware', ))#'asic'

	args = parser.parse_args()

	if args.action == 'sim':
		# from arachne.core.sim import run_sims
		# run_sims(pkg = 'remiru/sim', result_dir = 'build')
		return 0
	elif args.action == 'build':
		build(args.buildAs)
		return 0
