if {$argc != 2} {error "Expected the routed checkpoint and evidence directory"}
if {[version -short] ne "2025.2"} {error "Expected Vivado 2025.2"}
set_param general.maxThreads 2
set dcp [lindex $argv 0]
set output [lindex $argv 1]
open_checkpoint $dcp
report_utilization -hierarchical -file [file join $output utilization-hierarchical.rpt]
report_utilization -file [file join $output utilization.rpt]
set f [open [file join $output primitive-census.tsv] w]
foreach cell [get_cells -hierarchical -quiet -filter {REF_NAME =~ RAM* || REF_NAME =~ URAM* || REF_NAME == DSP48E2 || REF_NAME == PS8}] {
    puts $f "[get_property NAME $cell]\t[get_property REF_NAME $cell]"
}
close $f
set gate [open [file join $output checkpoint.txt] w]
puts $gate "checkpoint_sha256 [lindex [exec sha256sum $dcp] 0]"
puts $gate "tool [version -short]"
puts $gate "part [get_property PART [current_design]]"
puts $gate "route_complete [report_route_status -boolean_check ROUTED_FULLY]"
puts $gate "clock_period_ns [get_property PERIOD [get_clocks clk_pl_0]]"
close $gate
exit
