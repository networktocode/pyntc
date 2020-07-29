unit_tests:
	flake8 .
	black --check .
	coverage run -m pytest ./test/unit -v

coverage_report:
	coverage report -m

coverage_html:
	coverage html

