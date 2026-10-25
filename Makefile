# make ppds      regenerate generated PPDs (thermal family: families/thermal/profiles -> ppd/)
# make emulator  build the ChromeOS print sandbox for the checker (once; downloads sources)
# make check     run the ChromeOS checker on every PPD in ppd/ (2-page test document)
.PHONY: ppds emulator check
ppds:
	python3 families/thermal/ppdgen.py --all
emulator:
	bash checker/emulator/build.sh
check: ppds
	python3 checker/chromeos_ppd_check.py ppd/*.ppd --pages 2
