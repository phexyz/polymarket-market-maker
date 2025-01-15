import sys
from poly_market_maker.app import App
from poly_market_maker.app_front_run import AppFrontRun


AppFrontRun(sys.argv[1:]).main()
