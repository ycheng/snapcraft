sudo apt-get update

sudo apt-get install -y \
	git \
	python3-dev \
	python3-pip \
	python3-mypy-extensions\
	python3-pyelftools\
	python3-jsonschema\
	python3-tabulate \
	python3-requests-unixsocket \
	python3-progressbar \
	python3-apt \
	python3-debian \
	python3-toml \
	python3-click \
	python3-pymacaroons \
	python3-simplejson \
	python3-pylxd \
	python3-gnupg \
	python3-lazr.uri \
	python3-lazr.restfulclient \
	python3-launchpadlib \
	execstack

sudo pip3 install catkin-pkg==0.4.20 requests-toolbelt raven==6.5.0 install typing-extensions

sudo mkdir -p /usr/share/snapcraft/

sudo cp -R keyrings/ extensions/ schema/ /usr/share/snapcraft/

