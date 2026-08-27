set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir ..]]
set build_dir [file normalize [file join $root_dir build vivado_core]]
set report_dir [file normalize [file join $root_dir results vivado_core]]
file mkdir $build_dir
file mkdir $report_dir

set part_name "xck26-sfvc784-2LV-c"
if {[info exists ::env(KDA_PART)]} {
    set part_name $::env(KDA_PART)
}

create_project kda_core $build_dir -force -part $part_name
set_property target_language Verilog [current_project]
read_verilog -sv [file join $root_dir rtl kda_state_bank.sv]
read_verilog -sv [file join $root_dir rtl kda_core.sv]
synth_design -top kda_core -part $part_name
create_clock -name kda_clock -period 10.000 [get_ports clk]
set_false_path -from [get_ports rst_n]
opt_design
place_design
phys_opt_design
route_design
report_utilization -hierarchical -file [file join $report_dir utilization.rpt]
report_timing_summary -delay_type min_max -report_unconstrained -check_timing_verbose -file [file join $report_dir timing_summary.rpt]
report_power -file [file join $report_dir power.rpt]
write_checkpoint -force [file join $report_dir kda_core_routed.dcp]
puts "KDA_CORE_BUILD_COMPLETE reports=$report_dir"
