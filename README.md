# quota_manager
Python application for OpenWRT quota management and throttling.

Requires https://github.com/broskic29/openwrt-builder/tree/develop

To run:
pipenv run quota_manager

[Pytest]
To run pytest unit tests only:
pipenv run pytest -q

To run a specific unit test:
pipenv run pytest -q {test_name.py}

To run integration only (already as root):
pipenv run pytest -m integration -q

To run a specific integration test (already as root): 
pipenv run pytest -m integration -q {test_name.py}