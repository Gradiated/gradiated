if {$argc != 1} {
    puts stderr "usage: vivado -mode batch -source vivado/program_kv260.tcl -tclargs results/kv260/kda_kv260.bit"
    exit 2
}
set bitstream [file normalize [lindex $argv 0]]
if {![file exists $bitstream]} {
    puts stderr "bitstream not found: $bitstream"
    exit 2
}
open_hw_manager
connect_hw_server -allow_non_jtag
open_hw_target
set devices [get_hw_devices -quiet xck26*]
if {[llength $devices] == 0} {
    puts stderr "No xck26 device was found. Check KV260 power and the micro-USB JTAG cable."
    exit 3
}
set device [lindex $devices 0]
current_hw_device $device
refresh_hw_device -update_hw_probes false $device
set_property PROGRAM.FILE $bitstream $device
program_hw_devices $device
refresh_hw_device $device
puts "KDA_KV260_PROGRAM_COMPLETE device=$device bitstream=$bitstream"
