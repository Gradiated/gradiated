# Complete candidate PS/AXI/neural build and offline programming-file preparation.
# Run each phase in a fresh bounded Vivado 2025.2 process, at most two threads:
#   -tclargs generate <candidate.xpr> <fresh-ignored-output>  (180 s)
#   -tclargs synth    <generated-project.xpr> <output>      (600 s)
#   -tclargs source-audit <generated-project.xpr> <output>  (180 s, no synthesis)
#   -tclargs opt|place|route <input.dcp> <output>            (600 s each)
#   -tclargs reports  <input.dcp> <output>                  (180 s)
#   -tclargs bitstream <accepted-routed.dcp> <output>       (180 s)
# The caller must enforce these wall limits and reap the whole process group.
# The bitstream phase emits only an offline candidate .bit programming file;
# it does not configure PS software, clocks or reset on a physical board.
# No launch_runs, child synthesis jobs, hardware access, XSA, boot/OS image,
# firmware, dependency download or board-image compatibility claim is included.

if {$argc != 3} {error "Require phase, input XPR/DCP and ignored output directory"}
lassign $argv phase input output
if {$phase ni {generate synth source-audit opt place route reports bitstream}} {error "Unknown candidate build phase: $phase"}
set script_path [file normalize [info script]]
set workstream [file dirname [file dirname $script_path]]
set repo [file dirname [file dirname $workstream]]
set runtime_root [file normalize [file join $repo .agents runtime fpga-inference]]
set input [file normalize $input]
set output [file normalize $output]
foreach path [list $input $output] {
    if {![string match "${runtime_root}/*" $path]} {error "Input/output must be under ignored $runtime_root"}
}
if {![file isfile $input]} {error "Input file is missing: $input"}
if {[version -short] ne "2025.2"} {error "This candidate requires installed Vivado 2025.2"}
if {[current_project -quiet] ne ""} {error "Run each phase in a fresh Vivado process"}
file mkdir $output
cd $output
set_param general.maxThreads 2

proc sha256 {path} {
    if {![file isfile $path]} {error "Source disappeared: $path"}
    return [lindex [exec /usr/bin/sha256sum -- $path] 0]
}
proc pin_sources {paths destination} {
    set result [dict create]
    set stream [open $destination w]
    foreach path [lsort -unique $paths] {
        set path [file normalize $path]
        set digest [sha256 $path]
        dict set result $path $digest
        puts $stream "$digest\t$path"
    }
    close $stream
    return $result
}
proc check_part {} {
    if {[get_property PART [current_project]] ne "xck26-sfvc784-2LV-c"} {
        error "Candidate device differs from the selected commercial K26"
    }
}
set neural_pins [dict create \
    fixed_scalar d34a86f812f7c3c362aba754430ddd3fe161bb917f066fdbb84ce95291eba690 \
    mac32 9db772ac21e7c0101cfbca0c6f52487cb6a88f24f20b76af76cd1f70c2f7c4b4 \
    qk_rope acd022f4ffcd540875b37586b0c6fa058873300bb7ea16860bb532b152700662 \
    kv_cache 1a97adbdd49e66d6938b4c934185be86a6d3b2a76bc1b85d5df624aacf3c3b48 \
    frontend dcc8699ad4271af008f1b6dc8f0745ea0435aea87442477217e0be374c5c9d6a \
    attention 3aa9cb030aae469ba235ae9092ea255866cc960ab57adb666117e8e799cbf93d \
    dense 561e82c83a15071ed45e251329a15fc212b9b1dca4fdb30ed24b33d878613ac9 \
    rmsnorm de661d481540bacca74e6b28e6d9799daf4dafd9b3c0611781e27b8ec05ac1c0 \
    feedforward 030f2917a8c6df23e18da1d2ef5e3394833c070a22a0a676f4aace705d1253d0 \
    transformer d6de7cd2b36a5d6997eab489ec9488745a4c2d37f1b95dd18c79b15aef48d2b9 \
    axi_transformer 12b9d9800a3a0240052219cb40a4e56672605a44b8bd1b8b2bcfb4d873d9a4e5]
proc generated_sources {directory} {
    set result {}
    foreach path [glob -nocomplain -directory $directory *] {
        if {[file isdirectory $path]} {
            if {![string match *.cache $path] && ![string match *.runs $path]} {
                lappend result {*}[generated_sources $path]
            }
        } elseif {[string tolower [file extension $path]] in {
            .v .sv .vh .svh .vhd .vhdl .xdc .xci .bd .coe .mem .dat .mif .prj .xml .xpr
        }} {lappend result $path}
    }
    return $result
}
proc compiled_sources {} {
    global workstream neural_pins output
    set order [get_files -compile_order sources -used_in synthesis]
    set order [encoding convertfrom utf-8 [encoding convertto utf-8 $order]]
    set stream [open [file join $output compiled-neural-sources.tsv] w]
    dict for {name expected} $neural_pins {
        set matches {}
        foreach path $order {
            if {[file tail $path] eq "${name}.sv"} {lappend matches [file normalize $path]}
        }
        set tracked [file normalize [file join $workstream rtl ${name}.sv]]
        if {[llength $matches] != 1 || [lindex $matches 0] ne $tracked} {
            close $stream
            error "Compile order must contain exactly the tracked neural source $tracked: $matches"
        }
        if {[sha256 $tracked] ne $expected} {close $stream;error "Pinned neural bytes differ: $tracked"}
        puts $stream "$expected\t$tracked"
    }
    close $stream
    set closure $order
    foreach path [get_files -quiet -all] {if {[file isfile $path]} {lappend closure $path}}
    lappend closure {*}[generated_sources [get_property DIRECTORY [current_project]]]
    set closure [encoding convertfrom utf-8 [encoding convertto utf-8 $closure]]
    pin_sources $closure [file join $output synthesis-source-closure.tsv]
    set stream [open [file join $output compile-order.tsv] w]
    foreach path $order {puts $stream "[sha256 $path]\t[file normalize $path]"}
    close $stream
}
proc check_identity {} {
    if {[get_property TOP [current_design]] ne "tiny_ps_axi_wrapper"} {
        error "Checkpoint TOP is not the complete tiny_ps_axi_wrapper"
    }
    if {[llength [get_cells -hier -quiet -filter {REF_NAME == PS8}]] != 1} {
        error "Complete candidate must contain exactly one PS8 primitive"
    }
    if {[llength [get_cells -hier -quiet -filter {REF_NAME == BUFG_PS}]] != 1} {
        error "Complete candidate must contain exactly one PS clock buffer"
    }
}
proc clock_topology {destination {require_complete_route 0}} {
    check_identity
    set ps [get_cells -hier -quiet -filter {REF_NAME == PS8}]
    set buffer [get_cells -hier -quiet -filter {REF_NAME == BUFG_PS}]
    set source [get_pins -quiet -of_objects $ps -filter {REF_PIN_NAME == "PLCLK[0]"}]
    set buffer_in [get_pins -quiet -of_objects $buffer -filter {REF_PIN_NAME == I}]
    set buffer_out [get_pins -quiet -of_objects $buffer -filter {REF_PIN_NAME == O}]
    if {[llength $source] != 1 || [llength $buffer_in] != 1 || [llength $buffer_out] != 1} {
        error "Missing PS PLCLK0 or clock-buffer pins"
    }
    set source_nets [get_nets -quiet -segments -of_objects $source]
    set source_loads [get_pins -quiet -leaf -of_objects $source_nets -filter {DIRECTION == IN}]
    if {[llength $source_loads] != 1 || $source_loads ne $buffer_in} {
        error "PS8 PLCLK0 must drive the real BUFG_PS input directly"
    }
    set clock [get_clocks -quiet clk_pl_0]
    set clock_sources [get_property SOURCE_PINS $clock]
    if {[llength [get_clocks -quiet]] != 1 || [llength $clock] != 1 ||
        abs([get_property PERIOD $clock] - 20.0) > 0.000001 ||
        [llength $clock_sources] != 1 || [lindex $clock_sources 0] ne [get_property NAME $source]} {
        error "Candidate must have one 20 ns clk_pl_0 sourced by the actual PS8 PLCLK0"
    }
    set output_nets [get_nets -quiet -segments -of_objects $buffer_out]
    set clock_sinks [get_pins -quiet -leaf -of_objects $output_nets -filter {IS_CLOCK == 1}]
    set neural_sinks [filter $clock_sinks {NAME =~ tiny_ps_axi_i/neural/*}]
    set neural_port [get_pins -quiet tiny_ps_axi_i/neural/aclk]
    if {![llength $neural_sinks] || [llength $neural_port] != 1 ||
        [get_clocks -quiet -of_objects $neural_sinks] ne $clock ||
        [get_clocks -quiet -of_objects $neural_port] ne $clock} {
        error "Neural aclk and actual neural clock sinks must use the PS8/BUFG_PS clock domain"
    }
    set gaps [report_route_status -return_nets -route_type GAPS]
    set clock_gaps {}
    foreach net $gaps {
        foreach segment [get_nets -quiet -segments $net] {
            if {[lsearch -exact [concat $source_nets $output_nets] $segment] >= 0} {
                lappend clock_gaps $net;break
            }
        }
    }
    set stream [open $destination w]
    puts $stream "design_top\t[get_property TOP [current_design]]"
    puts $stream "design_name\t[get_property NAME [current_design]]"
    puts $stream "ps8\t$ps"
    puts $stream "source_pin\t$source"
    puts $stream "buffer\t$buffer"
    puts $stream "buffer_input\t$buffer_in"
    puts $stream "buffer_output\t$buffer_out"
    puts $stream "neural_aclk\t$neural_port"
    puts $stream "neural_clock_pins\t[llength $neural_sinks]"
    puts $stream "clock_domain\t$clock"
    puts $stream "clock_period_ns\t[get_property PERIOD $clock]"
    puts $stream "sealed_expected_derived_clock_hz\t49999500"
    puts $stream "clock_gap_nets\t[llength $clock_gaps]"
    puts $stream "require_complete_route\t$require_complete_route"
    foreach net $clock_gaps {puts $stream "clock_gap_net\t$net"}
    foreach pin $neural_sinks {puts $stream "neural_clock_pin\t$pin"}
    close $stream
    # Placement does not complete physical routes. Keep graph/domain checks
    # strict at every stage, and require gap-free routing only after route
    # and for final reports. Pending gaps remain explicit in earlier evidence.
    if {$require_complete_route && [llength $clock_gaps]} {
        error "PS-to-neural clock has a physical routing gap"
    }
}
proc timing_coverage {timing_path destination} {
    set stream [open $timing_path r];set text [read $stream];close $stream
    if {![regexp {checking no_clock \(([0-9]+)\)} $text -> native_count] ||
        ![regexp {checking unconstrained_internal_endpoints \(([0-9]+)\)} $text -> unconstrained]} {
        error "Missing native timing-coverage counts"
    }
    if {![regexp {(?s)1\. checking no_clock \([0-9]+\)\s*-+\s*(.*?)\n2\. checking} $text -> section]} {
        error "Missing verbose no_clock pin section"
    }
    set ps [get_cells -hier -quiet -filter {REF_NAME == PS8}]
    set allowed {EMIOENET0MDIOMDC EMIOENET1MDIOMDC EMIOENET2MDIOMDC EMIOENET3MDIOMDC EMIOSDIO0CLKOUT EMIOSDIO1CLKOUT EMIOSPI0SCLKO EMIOSPI1SCLKO}
    set unused 0;set active 0;set observed {}
    set stream [open $destination w]
    puts $stream "native_no_clock\t$native_count"
    puts $stream "unconstrained_internal_endpoints\t$unconstrained"
    foreach line [split $section \n] {
        set name [string trim $line]
        if {$name eq "" || [string match "There are *" $name]} {continue}
        lappend observed $name
        set ref [file tail $name]
        set pin [get_pins -quiet -of_objects $ps -filter [list REF_PIN_NAME == $ref]]
        if {$ref ni $allowed || [llength $pin] != 1 || [get_property NAME $pin] ne $name ||
            [get_property DIRECTION $pin] ne "OUT"} {
            incr active;puts $stream "unclocked_active_pin\t$name";continue
        }
        set nets [get_nets -quiet -segments -of_objects $pin]
        set sinks {}
        if {[llength $nets]} {set sinks [get_pins -quiet -leaf -of_objects $nets -filter {DIRECTION == IN}]}
        puts $stream "ps_clock_output\t$name\tOUT\t[llength $sinks]"
        if {[llength $sinks]} {incr active} else {incr unused}
    }
    puts $stream "unused_ps_clock_outputs\t$unused"
    puts $stream "unclocked_active_pins\t$active"
    close $stream
    if {[llength $observed] != $native_count || [llength [lsort -unique $observed]] != $native_count ||
        $active != 0 || $unconstrained != 0 || $unused != $native_count} {
        error "Active/unidentified clock pins or internal endpoints lack timing coverage"
    }
    return [list $native_count $unused $active $unconstrained]
}
proc drc_state {} {
    set result [dict create]
    foreach rule [get_drc_checks] {
        dict set result [get_property NAME $rule] [list \
            [get_property SEVERITY $rule] [get_property IS_ENABLED $rule] \
            [get_property MAX_MESSAGES $rule] [get_property MAX_NAMES $rule]]
    }
    return [encoding convertfrom utf-8 [encoding convertto utf-8 $result]]
}
proc fresh_drc_defaults {} {
    global output
    # Linking this empty metadata-only netlist initializes the installed rule
    # set, including the tool-created AMD_NETLIST-14 utilization rule. No
    # synthesis is run and no rule is reset, weakened, suppressed or waived.
    set baseline [file join $output rule_baseline.edf]
    set stream [open $baseline w]
    puts $stream {(edif rule_baseline (edifVersion 2 0 0) (edifLevel 0) (keywordMap (keywordLevel 0)) (library work (edifLevel 0) (technology (numberDefinition)) (cell rule_baseline (cellType GENERIC) (view netlist (viewType NETLIST) (interface)))) (design rule_baseline (cellRef rule_baseline (libraryRef work))))}
    close $stream
    read_edif $baseline
    link_design -top rule_baseline -part xck26-sfvc784-2LV-c
    set result [drc_state]
    set stream [open [file join $output drc-defaults.tsv] w]
    foreach name [lsort [dict keys $result]] {puts $stream "$name\t[join [dict get $result $name] \t]"}
    close $stream
    close_project
    return $result
}
proc audit_constraints {destination} {
    global drc_defaults
    set current [drc_state]
    set changes {}
    foreach name [lsort -unique [concat [dict keys $drc_defaults] [dict keys $current]]] {
        if {![dict exists $drc_defaults $name] || ![dict exists $current $name] ||
            [dict get $drc_defaults $name] ne [dict get $current $name]} {lappend changes $name}
    }
    set waivers [get_waivers -quiet -type ALL]
    set loop_allow [get_nets -hier -quiet -filter {ALLOW_COMBINATORIAL_LOOPS == 1}]
    set route_overrides [get_nets -hier -quiet -filter {CLOCK_DEDICATED_ROUTE != "" && CLOCK_DEDICATED_ROUTE != TRUE}]
    set stream [open $destination w]
    puts $stream "default_rules [dict size $drc_defaults]"
    puts $stream "changed_rules [llength $changes]"
    puts $stream "waiver_objects [llength $waivers]"
    puts $stream "loop_allow_nets [llength $loop_allow]"
    puts $stream "clock_route_overrides [llength $route_overrides]"
    foreach name $changes {puts $stream "changed_rule $name"}
    foreach object [concat $waivers $loop_allow $route_overrides] {
        puts $stream [report_property -all -return_string $object]
    }
    close $stream
    if {[llength $changes] || [llength $waivers] || [llength $loop_allow] || [llength $route_overrides]} {
        error "Constraint audit found changed DRC defaults, waiver objects, loop allowance or clock-route overrides"
    }
}
proc write_structure {destination} {
    check_identity
    set blackboxes [get_cells -hierarchical -quiet -filter {IS_BLACKBOX == 1}]
    set latches [get_cells -hierarchical -quiet -filter {REF_NAME =~ LD*}]
    set stream [open $destination w]
    puts $stream "blackboxes [llength $blackboxes]"
    puts $stream "latches [llength $latches]"
    puts $stream "design_top [get_property TOP [current_design]]"
    puts $stream "processing_system_primitives [llength [get_cells -hierarchical -quiet -filter {REF_NAME == PS8}]]"
    foreach kind {DSP48E2 RAMB36E2 RAMB18E2 BUFGCE BUFGCTRL BUFG_PS} {
        puts $stream "$kind [llength [get_cells -hierarchical -quiet -filter [list REF_NAME == $kind]]]"
    }
    foreach cell [concat $blackboxes $latches] {
        puts $stream [report_property -all -return_string $cell]
    }
    close $stream
    if {[llength $blackboxes]} {error "Complete candidate contains unresolved black boxes"}
    if {[llength $latches]} {error "Complete candidate contains inferred latch cells; inspect structure report"}
}

set drc_defaults {}
if {$phase in {synth opt place route reports bitstream}} {set drc_defaults [fresh_drc_defaults]}
set pin_paths [list $script_path $input]
foreach name {fixed_scalar mac32 qk_rope kv_cache frontend attention dense rmsnorm feedforward transformer axi_transformer} {
    set tracked [file join $workstream rtl ${name}.sv]
    if {[sha256 $tracked] ne [dict get $neural_pins $name]} {error "Pinned neural bytes differ: $tracked"}
    lappend pin_paths $tracked
}
if {$phase in {generate synth source-audit}} {
    if {[file extension $input] ne ".xpr"} {error "Project phase requires an XPR input"}
    open_project -read_only $input
    check_part
    if {[get_property BOARD_PART [current_project]] ne "xilinx.com:kv260_som:part0:1.4"} {
        error "Project does not use the selected KV260 SOM 1.4 preset"
    }
    set board [get_board_parts -quiet xilinx.com:kv260_som:part0:1.4]
    set board_file [get_property FILE_NAME $board]
    set preset_file [file join [file dirname $board_file] preset_s4.xml]
    foreach {path expected} [list \
        $board_file edebd35cff91551842b06603426d0478d9ef6bc92106ff0b9eb0c741b8d354fd \
        $preset_file 26d44b28017b59e6d31d1292d1436d68a24ee67fef45885c524e6873ff99be3a] {
        if {[sha256 $path] ne $expected} {error "Installed board/preset pin differs: $path"}
        lappend pin_paths $path
    }
    foreach path [get_files -quiet -all] {
        if {[file isfile $path] && [file extension $path] in {.bd .v .sv .vhd .xdc .xci}} {
            lappend pin_paths $path
        }
    }
}
# Detach filename strings from Vivado-managed get_files objects before copying
# or closing a project. Retaining those native objects across save_project_as
# can otherwise abort this installed Tcl runtime when their paths are reused.
set pin_paths [encoding convertfrom utf-8 [encoding convertto utf-8 $pin_paths]]
set pins_before [pin_sources $pin_paths [file join $output inputs-before.tsv]]

if {$phase eq "generate"} {
    set project_dir [file join $output project]
    if {[file exists $project_dir]} {error "Refusing to overwrite an existing generated project"}
    save_project_as tiny_ps_axi_build $project_dir -exclude_run_results
    set bd [get_files -quiet */tiny_ps_axi.bd]
    if {[llength $bd] != 1} {error "Expected one top-level tiny_ps_axi block design"}
    if {![string match "${project_dir}/*" [file normalize $bd]]} {
        error "Project copy did not isolate the block design from the input project"
    }
    # Global mode synthesizes generated IP RTL together with the full top;
    # this does not create or launch separate out-of-context synthesis runs.
    set_property SYNTH_CHECKPOINT_MODE None $bd
    open_bd_design $bd
    # The installed API accepts an IP instance, rather than a BD cell object.
    set neural_ip [get_ips -quiet [get_property CONFIG.Component_Name [get_bd_cells neural]]]
    if {[llength $neural_ip] != 1} {error "Cannot resolve the actual neural module-reference IP"}
    update_module_reference $neural_ip
    validate_bd_design
    save_bd_design
    generate_target all $bd
    set wrappers [make_wrapper -top $bd]
    if {[llength $wrappers] != 1 || ![file isfile $wrappers]} {error "Expected one generated HDL wrapper"}
    add_files -norecurse $wrappers
    set_property top tiny_ps_axi_wrapper [get_filesets sources_1]
    update_compile_order -fileset sources_1
    compiled_sources
    set stream [open [file join $output generated-project.txt] w]
    puts $stream "project [file join $project_dir tiny_ps_axi_build.xpr]"
    puts $stream "block_design $bd"
    puts $stream "wrapper $wrappers"
    puts $stream "synth_checkpoint_mode [get_property SYNTH_CHECKPOINT_MODE $bd]"
    puts $stream "top [get_property TOP [get_filesets sources_1]]"
    puts $stream "compile_order [get_files -compile_order sources -used_in synthesis]"
    close $stream
    puts "CANDIDATE_BUILD_PROJECT=[file join $project_dir tiny_ps_axi_build.xpr]"
} elseif {$phase in {synth source-audit}} {
    set bd [get_files -quiet */tiny_ps_axi.bd]
    if {[llength $bd] != 1 || [get_property SYNTH_CHECKPOINT_MODE $bd] ne "None"} {
        error "Input project must have its top block design in global synthesis mode"
    }
    if {[get_property TOP [get_filesets sources_1]] ne "tiny_ps_axi_wrapper"} {
        error "Input project top is not the complete generated board wrapper"
    }
    update_compile_order -fileset sources_1
    compiled_sources
    if {$phase eq "synth"} {
        synth_design -top tiny_ps_axi_wrapper -part xck26-sfvc784-2LV-c -flatten_hierarchy rebuilt
        write_checkpoint [file join $output synthesized.dcp]
        write_structure [file join $output structure.txt]
        audit_constraints [file join $output constraints-after.txt]
        report_utilization -file [file join $output utilization.rpt]
    }
} elseif {$phase in {opt place route}} {
    if {[file extension $input] ne ".dcp"} {error "Implementation phase requires a DCP input"}
    open_checkpoint $input
    check_part
    check_identity
    audit_constraints [file join $output constraints-before.txt]
    clock_topology [file join $output clock-domain-before.tsv]
    if {$phase eq "opt"} {opt_design}
    if {$phase eq "place"} {place_design}
    if {$phase eq "route"} {route_design}
    write_checkpoint [file join $output ${phase}.dcp]
    write_structure [file join $output structure.txt]
    audit_constraints [file join $output constraints-after.txt]
    clock_topology [file join $output clock-domain-after.tsv] [expr {$phase eq "route"}]
} else {
    if {[file extension $input] ne ".dcp"} {error "Reports/bitstream phase requires a DCP input"}
    open_checkpoint $input
    check_part
    write_structure [file join $output structure.txt]
    audit_constraints [file join $output constraints-before.txt]
    clock_topology [file join $output clock-domain.tsv] 1
    report_clocks -file [file join $output clocks.rpt]
    report_utilization -file [file join $output utilization.rpt]
    report_timing_summary -delay_type min_max -report_unconstrained -file [file join $output timing.rpt]
    check_timing -verbose -file [file join $output check-timing.rpt]
    lassign [timing_coverage [file join $output check-timing.rpt] [file join $output clock-coverage.tsv]] \
        native_no_clock unused_ps_clocks unclocked_active unconstrained_internal
    report_drc -file [file join $output drc.rpt]
    report_route_status -file [file join $output route-status.rpt]
    set worst_setup [get_timing_paths -quiet -delay_type max -max_paths 1]
    set worst_hold [get_timing_paths -quiet -delay_type min -max_paths 1]
    if {[llength $worst_setup] != 1 || [llength $worst_hold] != 1} {error "Missing full-design clocked timing paths"}
    set drc_errors [get_drc_violations -quiet -filter {SEVERITY == "Error" || SEVERITY == "Critical Warning"}]
    set stream [open [file join $output metrics.txt] w]
    puts $stream "scope candidate_full_PS_AXI_neural_no_board_compatibility_claim"
    puts $stream "setup_slack_ns [get_property SLACK $worst_setup]"
    puts $stream "hold_slack_ns [get_property SLACK $worst_hold]"
    puts $stream "drc_errors_or_critical_warnings [llength $drc_errors]"
    puts $stream "native_no_clock $native_no_clock"
    puts $stream "unused_ps_clock_outputs $unused_ps_clocks"
    puts $stream "unclocked_active_pins $unclocked_active"
    puts $stream "unconstrained_internal_endpoints $unconstrained_internal"
    puts $stream "fully_placed [report_route_status -boolean_check PLACED_FULLY]"
    puts $stream "fully_routed [report_route_status -boolean_check ROUTED_FULLY]"
    puts $stream "routing_errors [report_route_status -boolean_check ERRORS_IN_ROUTES]"
    puts $stream "unrouted_nets [llength [report_route_status -return_nets -route_type UNROUTED]]"
    puts $stream "partially_routed_nets [llength [report_route_status -return_nets -route_type PARTIAL]]"
    puts $stream "routing_gap_nets [llength [report_route_status -return_nets -route_type GAPS]]"
    foreach clock [get_clocks -quiet] {puts $stream "clock $clock period_ns [get_property PERIOD $clock]"}
    close $stream
    audit_constraints [file join $output constraints-after.txt]
    set stream [open [file join $output routing-gaps.txt] w]
    foreach net [report_route_status -return_nets -route_type GAPS] {
        puts $stream [report_property -all -return_string $net]
    }
    close $stream
    if {[llength $drc_errors]} {error "Complete candidate has DRC errors/critical warnings; no severity waivers are permitted"}
    if {$phase eq "bitstream"} {
        # The caller additionally requires the accepted numerical gate and an
        # accepted final-report predecessor for this exact routed checkpoint.
        # Repeat all native final checks here before producing a candidate.
        set stream [open [file join $output timing.rpt] r]
        set timing_text [read $stream]
        close $stream
        set fully_placed [report_route_status -boolean_check PLACED_FULLY]
        set fully_routed [report_route_status -boolean_check ROUTED_FULLY]
        set routing_errors [report_route_status -boolean_check ERRORS_IN_ROUTES]
        set unrouted [llength [report_route_status -return_nets -route_type UNROUTED]]
        set partial [llength [report_route_status -return_nets -route_type PARTIAL]]
        set gaps [llength [report_route_status -return_nets -route_type GAPS]]
        set setup_slack [get_property SLACK $worst_setup]
        set hold_slack [get_property SLACK $worst_hold]
        if {!$fully_placed || !$fully_routed || $routing_errors || $unrouted || $partial || $gaps ||
            $native_no_clock != 0 || $unclocked_active != 0 || $unconstrained_internal != 0 ||
            $setup_slack < 0 || $hold_slack < 0 ||
            [string first "All user specified timing constraints are met." $timing_text] < 0} {
            error "Candidate programming-file preparation requires complete, gap-free routing and all timing/clock coverage gates"
        }
        set bitstream [file join $output offline-candidate.bit]
        if {[file exists $bitstream]} {error "Refusing to overwrite an existing candidate bitstream"}
        set stream [open [file join $output bitstream-prerequisites.txt] w]
        puts $stream "scope offline_candidate_only_not_deployed"
        puts $stream "fully_placed $fully_placed"
        puts $stream "fully_routed $fully_routed"
        puts $stream "routing_errors $routing_errors"
        puts $stream "unrouted_nets $unrouted"
        puts $stream "partially_routed_nets $partial"
        puts $stream "routing_gap_nets $gaps"
        puts $stream "native_no_clock $native_no_clock"
        puts $stream "unclocked_active_pins $unclocked_active"
        puts $stream "unconstrained_internal_endpoints $unconstrained_internal"
        puts $stream "setup_slack_ns $setup_slack"
        puts $stream "hold_slack_ns $hold_slack"
        puts $stream "requires_actual_board_PS_clock_reset_MMIO_software_compatibility 1"
        close $stream
        # Do not set configuration properties, waive DRC, request .bin/.rbt,
        # export XSA or invoke hardware manager. Keep the accepted DCP intact.
        write_bitstream $bitstream
        if {![file isfile $bitstream] || [file size $bitstream] <= 0} {
            error "Vivado did not produce a nonempty offline candidate bitstream"
        }
        audit_constraints [file join $output constraints-after-bitstream.txt]
        clock_topology [file join $output clock-domain-after-bitstream.tsv] 1
        puts "CANDIDATE_BITSTREAM_PATH=$bitstream"
    }
}

set pins_after [pin_sources $pin_paths [file join $output inputs-after.tsv]]
if {$pins_before ne $pins_after} {error "An input source changed during the build phase"}
# get_files returns Vivado-managed Tcl objects. Finish their path/hash use
# before closing the project, so no stale file objects cross that boundary.
if {$phase eq "generate"} {close_project}
puts "PASS CANDIDATE_BUILD $phase"
if {$phase eq "bitstream"} {
    puts "CANDIDATE_BITSTREAM_ONLY"
    puts "NOT_DEPLOYED"
} else {
    puts "NOT_A_BOARD_IMAGE_OR_BITSTREAM"
}
exit
