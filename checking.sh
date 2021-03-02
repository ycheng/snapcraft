black snapcraft/plugins/v2/conda.py
pycodestyle --ignore=E501,W503 \
	snapcraft/plugins/v2/conda.py
# xxxxx
python3 -m testtools.run  tests.unit.plugins.v2.test_conda
