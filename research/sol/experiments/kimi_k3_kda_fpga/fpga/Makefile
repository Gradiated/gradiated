PYTHON ?= python3
IVERILOG ?= iverilog
VVP ?= vvp
VERILATOR ?= verilator
YOSYS ?= yosys
CC ?= cc
BUILD_DIR := build
FIXTURE_DIR := sim/fixtures
RTL := rtl/kda_state_bank.sv rtl/kda_core.sv rtl/kda_axi_top.sv

.PHONY: all check fixtures fixtures-target python-test sim-core sim-target sim-axi lint tcl-check synth-small synth-kv260 lane-sweep host host-reference vivado-core vivado-kv260 vivado-kv260-l16 vivado-kv260-l32 clean

all: check

check: python-test sim-core sim-target sim-axi lint tcl-check synth-small host-reference

fixtures:
	$(PYTHON) sim/kda_reference.py --output-dir $(FIXTURE_DIR) --head-dim 16 --tokens 3 --seed 0x4b444131

fixtures-target:
	$(PYTHON) sim/kda_reference.py --output-dir sim/fixtures_target --head-dim 128 --tokens 3 --seed 0x4b444131

python-test:
	PYTHONPATH=sim $(PYTHON) -m unittest discover -s sim -p 'test_*.py' -v

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

sim-core: fixtures | $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -s tb_kda_core -o $(BUILD_DIR)/tb_kda_core rtl/kda_state_bank.sv rtl/kda_core.sv sim/tb_kda_core.sv
	$(VVP) $(BUILD_DIR)/tb_kda_core

sim-target: fixtures-target | $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -DKDA_TARGET -DKDA_TARGET_L16 -s tb_kda_core -o $(BUILD_DIR)/tb_kda_core_d128_l16 rtl/kda_state_bank.sv rtl/kda_core.sv sim/tb_kda_core.sv
	$(VVP) $(BUILD_DIR)/tb_kda_core_d128_l16
	$(IVERILOG) -g2012 -Wall -DKDA_TARGET -DKDA_TARGET_L32 -s tb_kda_core -o $(BUILD_DIR)/tb_kda_core_d128_l32 rtl/kda_state_bank.sv rtl/kda_core.sv sim/tb_kda_core.sv
	$(VVP) $(BUILD_DIR)/tb_kda_core_d128_l32

sim-axi: fixtures | $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -s tb_kda_axi -o $(BUILD_DIR)/tb_kda_axi $(RTL) sim/tb_kda_axi.sv
	$(VVP) $(BUILD_DIR)/tb_kda_axi

lint:
	LC_ALL=C LANG=C $(VERILATOR) --lint-only --timing -Wall -Wno-fatal -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNUSEDSIGNAL --top-module kda_axi_top $(RTL)

tcl-check:
	tclsh scripts/check_tcl_syntax.tcl vivado/build_core.tcl vivado/build_kv260.tcl vivado/program_kv260.tcl

synth-small: | $(BUILD_DIR)
	$(YOSYS) -q -l $(BUILD_DIR)/yosys_small.log yosys/core_small.ys

synth-kv260: | $(BUILD_DIR)
	$(YOSYS) -q -l $(BUILD_DIR)/yosys_kv260.log yosys/core_kv260.ys

lane-sweep:
	$(PYTHON) scripts/run_lane_sweep.py

host: | $(BUILD_DIR)
	$(CC) -std=c11 -O2 -Wall -Wextra -Werror host/kda_kv260_test.c -o $(BUILD_DIR)/kda_kv260_test

host-reference: host
	PYTHONPATH=sim $(PYTHON) sim/check_host_reference.py $(BUILD_DIR)/kda_kv260_test

vivado-core:
	vivado -mode batch -nojournal -nolog -source vivado/build_core.tcl

vivado-kv260:
	vivado -mode batch -nojournal -nolog -source vivado/build_kv260.tcl

vivado-kv260-l16:
	KDA_HEAD_DIM=128 KDA_LANES=16 vivado -mode batch -nojournal -nolog -source vivado/build_kv260.tcl

vivado-kv260-l32:
	KDA_HEAD_DIM=128 KDA_LANES=32 vivado -mode batch -nojournal -nolog -source vivado/build_kv260.tcl

clean:
	rm -rf $(BUILD_DIR) sim/fixtures sim/fixtures_target results/vivado_core results/kv260
