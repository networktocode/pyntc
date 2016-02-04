unit_tests:
	coverage run -m unittest discover ./test/unit -v

coverage_report:
	coverage report -m

coverage_html:
	coverage html

