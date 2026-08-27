set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set head_dim 128
set lanes 16
if {[info exists ::env(KDA_HEAD_DIM)]} {
    set head_dim $::env(KDA_HEAD_DIM)
}
if {[info exists ::env(KDA_LANES)]} {
    set lanes $::env(KDA_LANES)
}
if {$head_dim % $lanes != 0} {
    puts stderr "KDA_HEAD_DIM must be divisible by KDA_LANES"
    exit 2
}
set variant "d${head_dim}_l${lanes}"
set build_dir [file normalize [file join $root_dir build vivado_kv260 $variant]]
set artifact_dir [file normalize [file join $root_dir results kv260 $variant]]
file mkdir $build_dir
file mkdir $artifact_dir

set board_part ""
if {[info exists ::env(KDA_BOARD_PART)]} {
    set board_part $::env(KDA_BOARD_PART)
} else {
    set board_candidates [get_board_parts -quiet *kv260*]
    if {[llength $board_candidates] > 0} {
        set board_part [lindex [lsort -dictionary $board_candidates] end]
    }
}
if {$board_part eq ""} {
    puts stderr "No KV260 board part was found. Install the KV260 board files or set KDA_BOARD_PART."
    puts stderr "Available Kria board parts: [get_board_parts -quiet *kria*]"
    exit 2
}

set part_name [get_property PART_NAME [get_board_parts $board_part]]
create_project kda_kv260 $build_dir -force -part $part_name
set_property board_part $board_part [current_project]
set_property target_language Verilog [current_project]
read_verilog [file join $root_dir rtl kda_state_bank.sv]
read_verilog [file join $root_dir rtl kda_core.sv]
read_verilog [file join $root_dir rtl kda_axi_top.sv]
set_property file_type Verilog [get_files [file join $root_dir rtl kda_state_bank.sv]]
set_property file_type Verilog [get_files [file join $root_dir rtl kda_core.sv]]
set_property file_type Verilog [get_files [file join $root_dir rtl kda_axi_top.sv]]

create_bd_design system
create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:* ps
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset "1"} [get_bd_cells ps]
set_property -dict [list CONFIG.PSU__USE__M_AXI_GP0 {1} CONFIG.PSU__FPGA_PL0_ENABLE {1} CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100}] [get_bd_cells ps]

create_bd_cell -type module -reference kda_axi_top kda
set_property -dict [list CONFIG.HEAD_DIM $head_dim CONFIG.LANES $lanes] [get_bd_cells kda]
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:* interconnect
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells interconnect]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:* reset
set_property -dict [list CONFIG.C_EXT_RESET_HIGH {0}] [get_bd_cells reset]

connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_HPM0_FPD] [get_bd_intf_pins interconnect/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins interconnect/M00_AXI] [get_bd_intf_pins kda/S_AXI]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins interconnect/aclk]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins reset/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins kda/s_axi_aclk]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins ps/maxihpm0_fpd_aclk]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins ps/maxihpm1_fpd_aclk]
connect_bd_net [get_bd_pins ps/pl_resetn0] [get_bd_pins reset/ext_reset_in]
connect_bd_net [get_bd_pins reset/interconnect_aresetn] [get_bd_pins interconnect/aresetn]
connect_bd_net [get_bd_pins reset/peripheral_aresetn] [get_bd_pins kda/s_axi_aresetn]

assign_bd_address
set kda_segments [get_bd_addr_segs -of_objects [get_bd_intf_pins kda/S_AXI]]
if {[llength $kda_segments] != 1} {
    puts stderr "Expected one KDA AXI address segment, found: $kda_segments"
    exit 3
}

validate_bd_design
save_bd_design
generate_target all [get_files system.bd]
set wrapper_path [make_wrapper -files [get_files system.bd] -top]
add_files -norecurse $wrapper_path
set_property top system_wrapper [current_fileset]

launch_runs synth_1 -jobs 8
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} {
    puts stderr "Synthesis did not complete: [get_property STATUS [get_runs synth_1]]"
    exit 4
}
open_run synth_1
report_utilization -hierarchical -file [file join $artifact_dir post_synth_utilization.rpt]
report_timing_summary -file [file join $artifact_dir post_synth_timing.rpt]
close_design

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} {
    puts stderr "Implementation did not complete: [get_property STATUS [get_runs impl_1]]"
    exit 5
}
open_run impl_1
report_utilization -hierarchical -file [file join $artifact_dir post_route_utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $artifact_dir post_route_timing.rpt]
report_power -file [file join $artifact_dir post_route_power.rpt]
close_design

set bitstream_path [file join $build_dir kda_kv260.runs impl_1 system_wrapper.bit]
if {![file exists $bitstream_path]} {
    puts stderr "Expected bitstream was not generated at $bitstream_path"
    exit 6
}
file copy -force $bitstream_path [file join $artifact_dir kda_kv260.bit]
write_hw_platform -fixed -include_bit -force -file [file join $artifact_dir kda_kv260.xsa]
puts "KDA_KV260_BUILD_COMPLETE board=$board_part variant=$variant artifacts=$artifact_dir"
