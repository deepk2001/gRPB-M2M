PY := .venv/bin/python
# Transport for the sample app: mqtt (gRPB-M2M) or grpc (plain gRPC over HTTP/2).
T ?= mqtt
APP := grpb_examples.temperature
SIM := $(PY) -m grpb_examples.sim
# Simulation for make sim / make sweep: farmnet, pulse or safeswitch.
S ?= farmnet

.PHONY: setup setup-pi broker cse smoke hal proto acme-patch test build sniff bench hub sensor fan \
        sim sweep plot dashboard evidence report

setup:        ## laptop: clone ACME, install Mosquitto, create .venv with library + examples
	scripts/setup-dev.sh

setup-pi:     ## Raspberry Pi: system packages + .venv
	scripts/setup-pi.sh

broker:       ## run Mosquitto (foreground)
	scripts/run-broker.sh

cse:          ## run ACME CSE (foreground)
	scripts/run-cse.sh $(ARGS)

smoke:        ## M1: oneM2M JSON over MQTT round trip + HTTP read-back (needs broker + cse)
	$(PY) tools/m1_smoke.py

hal:          ## check the sensor/relay backend (real Pi or simulator)
	$(PY) -m grpb_examples.hal

proto:        ## regenerate Python code from proto/ and examples/proto/
	PY=$(PY) scripts/gen-proto.sh

acme-patch:   ## (re)apply the Protobuf patch to vendor/acme and sync the codec
	scripts/patch-acme.sh

test:         ## library + sample-app tests (starts its own broker)
	$(PY) -m pytest -q

build:        ## build the pip package into dist/
	uv build --out-dir dist .

bench:        ## evidence: make bench ARGS="codec" | ARGS="e2e --n 300 --label laptop" | ARGS="report results/*"
	$(PY) tools/bench.py $(ARGS)

sniff:        ## show gRPB-M2M frames on the broker; Ctrl-C prints a size summary
	$(PY) tools/sniff.py $(ARGS)

# --- Temperature sample app. Pick the transport with T=mqtt|grpc, pass flags with ARGS="...". ---
hub:          ## hub server, e.g. make hub T=grpc
	$(PY) -m $(APP).hub --transport $(T) $(ARGS)

sensor:       ## sensor, e.g. make sensor ARGS="--id s1 --seed 1"
	$(PY) -m $(APP).sensor --transport $(T) $(ARGS)

fan:          ## fan controller, e.g. make fan ARGS="--sensor s1 --on 26 --off 24"
	$(PY) -m $(APP).fan --transport $(T) $(ARGS)

# --- Simulations: many nodes on one machine, data points for every claim (docs/SIMULATIONS.md). ---
sim:          ## one run, e.g. make sim S=farmnet ARGS="--nodes 50 --format pb" | S=pulse | S=safeswitch
	$(SIM) $(S) $(ARGS)

sweep:        ## grid of runs, e.g. make sweep S=farmnet ARGS="--vary format=json,cbor,pb -- --duration 30"
	$(SIM) sweep $(S) $(ARGS)

plot:         ## charts from results, e.g. make plot ARGS="results/<sweep>"
	$(SIM) plot $(ARGS)

dashboard:    ## FarmNet dashboard (HTTP/JSON view of the CSE) on port 8090
	$(SIM) dashboard $(ARGS)

evidence:     ## the full evidence matrix (all apps, formats, transports, networks) + charts; QUICK=1 for a dry run
	scripts/run-evidence.sh

report:       ## benefits report (.docx) from an evidence folder: make report EV=results/<time>-evidence-<label>
	[ -d tools/report/node_modules ] || (cd tools/report && npm install --silent)
	$(PY) tools/report/extract.py $(EV) tools/report/data.json
	node tools/report/build.js tools/report/data.json docs/gRPB-M2M-Benefits-Report.docx
