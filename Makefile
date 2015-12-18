system_tests:
	coverage run ./test/system/test_runner.py

unit_tests:
	coverage run -m unittest discover ./test/unit -v

