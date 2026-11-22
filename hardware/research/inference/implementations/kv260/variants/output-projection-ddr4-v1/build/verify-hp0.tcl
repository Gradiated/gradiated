if {$argc != 2} {error "Expected routed checkpoint and report destination"}
set_param general.maxThreads 2
open_checkpoint [lindex $argv 0]
set ps [get_cells -hierarchical -quiet -filter {REF_NAME == PS8}]
if {[llength $ps] != 1} {error "Expected one PS8"}
set out [open [lindex $argv 1] w]
foreach pin [get_pins -quiet -of_objects $ps] {
    set name [get_property REF_PIN_NAME $pin]
    if {![regexp {SAXIGP2|A?CLK.*GP2} $name]} {continue}
    set nets [get_nets -quiet -segments -of_objects $pin]
    if {![llength $nets]} {continue}
    set pins [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == OUT}]
    set sources [get_cells -quiet -of_objects $pins]
    set refs {}
    if {[llength $sources]} {set refs [lsort -unique [get_property REF_NAME $sources]]}
    set clocks [get_clocks -quiet -of_objects $pin]
    set kinds {}
    foreach net $nets {
        set kind [get_property -quiet TYPE $net]
        if {$kind ne ""} {lappend kinds $kind}
    }
    puts $out "$name\t$nets\t$refs\t[lsort -unique $kinds]\t$clocks"
}
close $out
exit
