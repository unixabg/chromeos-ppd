# make ppds      regenerate ppd/*.ppd from profiles/*.json
# make check     cupstestppd on every PPD
# make emulator  build the local ChromeOS print-pipeline emulator (once)
# make test      run every PPD through the ChromeOS emulator
.PHONY: ppds check emulator test
ppds:
	python3 tools/ppdgen.py --all
check: ppds
	@for f in ppd/*.ppd; do cupstestppd -W none "$$f" | head -1; done
emulator:
	bash tests/chromeos/build.sh
test: ppds
	python3 tests/chromeos/emulate.py --pages 2
