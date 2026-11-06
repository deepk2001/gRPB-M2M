PY := .venv/bin/python
# Transport for the sample app: mqtt (gRPB-M2M) or grpc (plain gRPC over HTTP/2).
T ?= mqtt
APP := grpb_examples.temperature

.PHONY: setup setup-pi broker cse smoke hal proto test build sniff hub sensor fan

setup:        ## laptop: clone ACME, install Mosquitto, create .venv with library + examples
	scripts/setup-dev.sh

setup-pi:     ## Raspberry Pi: system packages + .venv
	scripts/setup-pi.sh

broker:       ## run Mosquitto (foreground)
	scripts/run-broker.sh

cse:          ## run ACME CSE (foreground)
	scripts/run-cse.sh

smoke:        ## M1: oneM2M JSON over MQTT round trip + HTTP read-back (needs broker + cse)
	$(PY) tools/m1_smoke.py

hal:          ## check the sensor/relay backend (real Pi or simulator)
	$(PY) -m grpb_examples.hal

proto:        ## regenerate Python code from proto/ and examples/proto/
	PY=$(PY) scripts/gen-proto.sh

test:         ## library + sample-app tests (starts its own broker)
	$(PY) -m pytest -q

build:        ## build the pip package into dist/
	uv build --out-dir dist .

sniff:        ## show gRPB-M2M frames on the broker; Ctrl-C prints a size summary
	$(PY) tools/sniff.py $(ARGS)

# --- Temperature sample app. Pick the transport with T=mqtt|grpc, pass flags with ARGS="...". ---
hub:          ## hub server, e.g. make hub T=grpc
	$(PY) -m $(APP).hub --transport $(T) $(ARGS)

sensor:       ## sensor, e.g. make sensor ARGS="--id s1 --seed 1"
	$(PY) -m $(APP).sensor --transport $(T) $(ARGS)

fan:          ## fan controller, e.g. make fan ARGS="--sensor s1 --on 26 --off 24"
	$(PY) -m $(APP).fan --transport $(T) $(ARGS)
