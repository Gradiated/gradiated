# Candidate offline PS/AXI shell only. This does not create a board image.
# Invoke Vivado 2025.2 in a bounded, clean process using tools/rtl.py:
#   vivado -mode batch -source kv260-shell.tcl -tclargs <ignored-output-folder> ?50|100?
# No synthesis, IP output generation, implementation, hardware access, XSA,
# bitstream, firmware, operating-system image or boot-media write is performed.
# The provisional clock (100 MHz by default) and MMIO window require comparison with the
# physical board's existing firmware, operating system and device tree.

if {$argc > 2} {error "Expected an ignored output folder and optional clock MHz (50 or 100)"}
set requested_clock_mhz [expr {$argc == 2 ? [lindex $argv 1] : 100}]
if {$requested_clock_mhz ni {50 100}} {error "Candidate clock MHz must be exactly 50 or 100"}
set script_path [file normalize [info script]]
set workstream [file dirname [file dirname $script_path]]
set repo [file dirname [file dirname $workstream]]
set runtime_root [file normalize [file join $repo .agents runtime fpga-inference]]
set output [file normalize [expr {$argc >= 1 ? [lindex $argv 0] : [pwd]}]]
if {![string match "${runtime_root}/*" $output]} {
    error "Output must be a child of ignored $runtime_root"
}
if {[version -short] ne "2025.2"} {error "This candidate requires installed Vivado 2025.2"}
if {[current_project -quiet] ne ""} {error "Run this script in a fresh Vivado process"}
set project_dir [file join $output project]
if {[file exists $project_dir]} {error "Refusing to overwrite an existing candidate project"}
file mkdir $output
set_param general.maxThreads 2

proc pinned_sha256 {path expected} {
    if {![file isfile $path]} {error "Pinned installed file is missing: $path"}
    set actual [lindex [exec /usr/bin/sha256sum -- $path] 0]
    if {$actual ne $expected} {error "Installed file hash differs: $path ($actual)"}
    puts "CANDIDATE_PIN=$actual $path"
    return $actual
}

set board_part xilinx.com:kv260_som:part0:1.4
set device xck26-sfvc784-2LV-c
set board [get_board_parts -quiet $board_part]
if {[llength $board] != 1} {error "Pinned installed KV260 SOM 1.4 board part is unavailable"}
if {[get_property PART_NAME $board] ne $device} {error "Installed board device differs"}
set board_file [get_property FILE_NAME $board]
set preset_file [file join [file dirname $board_file] preset_s4.xml]
pinned_sha256 $board_file edebd35cff91551842b06603426d0478d9ef6bc92106ff0b9eb0c741b8d354fd
pinned_sha256 $preset_file 26d44b28017b59e6d31d1292d1436d68a24ee67fef45885c524e6873ff99be3a

create_project tiny_ps_axi_candidate $project_dir -part $device
set_property board_part $board_part [current_project]
set rtl_names {
    fixed_scalar mac32 qk_rope kv_cache frontend attention dense rmsnorm
    feedforward transformer axi_transformer
}
set rtl_sources {}
foreach name $rtl_names {
    set source [file join $workstream rtl ${name}.sv]
    if {![file isfile $source]} {error "Required actual RTL source is missing: $source"}
    lappend rtl_sources $source
}
add_files -norecurse $rtl_sources
# Vivado BD module references reject SystemVerilog top files. A temporary
# Verilog-2001 port wrapper exposes the unchanged actual SystemVerilog adapter;
# it contains no arithmetic, state, address conversion or substitute core.
set bridge_file [file join $output kv260_axi_bridge.v]
set bridge_text {
module kv260_axi_bridge (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK",
       X_INTERFACE_PARAMETER="XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET aresetn, FREQ_HZ __PS_PL0_FREQ_HZ__" *)
    input wire aclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST",
       X_INTERFACE_PARAMETER="XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *)
    input wire aresetn,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWADDR",
       X_INTERFACE_PARAMETER="XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 8" *)
    input wire [7:0] s_axi_awaddr,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output wire s_axi_awready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output wire s_axi_wready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output wire s_axi_bvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [7:0] s_axi_araddr,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output wire s_axi_arready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output wire [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output wire s_axi_rvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready
);
    axi_transformer actual (
        .aclk(aclk), .aresetn(aresetn),
        .s_axi_awaddr(s_axi_awaddr), .s_axi_awprot(s_axi_awprot),
        .s_axi_awvalid(s_axi_awvalid), .s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(s_axi_wstrb),
        .s_axi_wvalid(s_axi_wvalid), .s_axi_wready(s_axi_wready),
        .s_axi_bresp(s_axi_bresp), .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr), .s_axi_arprot(s_axi_arprot),
        .s_axi_arvalid(s_axi_arvalid), .s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp),
        .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready)
    );
endmodule
}
update_compile_order -fileset sources_1
foreach ip {
    xilinx.com:ip:zynq_ultra_ps_e:3.5
    xilinx.com:ip:smartconnect:1.0
    xilinx.com:ip:proc_sys_reset:5.0
    xilinx.com:ip:xlconstant:1.1
} {
    if {[llength [get_ipdefs -all -quiet $ip]] != 1} {
        error "Pinned installed IP is unavailable in this project: $ip"
    }
}

create_bd_design tiny_ps_axi
create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 ps
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e \
    -config {apply_board_preset "1"} [get_bd_cells ps]
# Retain the installed SOM DDR/MIO preset, with explicit candidate PL choices.
# These settings have not been checked against the board's running image.
set_property -dict [list \
    CONFIG.PSU__USE__M_AXI_GP0 {1} \
    CONFIG.PSU__USE__M_AXI_GP1 {0} \
    CONFIG.PSU__USE__M_AXI_GP2 {0} \
    CONFIG.PSU__MAXIGP0__DATA_WIDTH {32} \
    CONFIG.PSU__NUM_FABRIC_RESETS {1} \
    CONFIG.PSU__FPGA_PL0_ENABLE {1} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__SRCSEL {IOPLL} \
    CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ $requested_clock_mhz \
    CONFIG.PSU__FPGA_PL1_ENABLE {0}] [get_bd_cells ps]

# Preserve the preset's 33.333 MHz PS reference. Propagate the installed PS
# IP's derived clock metadata rather than asserting an inconsistent exact
# nominal clock annotation. Routed timing and board compatibility are separate.
set clock_hz [get_property CONFIG.FREQ_HZ [get_bd_pins ps/pl_clk0]]
if {![string is integer -strict $clock_hz] || $clock_hz <= 0} {
    error "The PS did not provide usable derived PL0 clock metadata: $clock_hz"
}
set bridge [open $bridge_file w]
puts $bridge [string map [list __PS_PL0_FREQ_HZ__ $clock_hz] $bridge_text]
close $bridge
add_files -norecurse $bridge_file
update_compile_order -fileset sources_1
create_bd_cell -type module -reference kv260_axi_bridge neural
if {[llength [get_bd_intf_pins -quiet neural/S_AXI]] != 1} {
    error "The actual RTL module did not infer its declared AXI4-Lite interface"
}
create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi
set_property -dict [list CONFIG.NUM_SI {1} CONFIG.NUM_MI {1}] [get_bd_cells axi]
create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 rst
# C_EXT_RESET_HIGH and the reset input's polarity are propagation-only in this
# installed IP. Connecting PS pl_resetn0 produces ACTIVE_LOW and value zero;
# assert both after validation instead of attempting a read-only override.
set_property CONFIG.C_AUX_RESET_HIGH {1} [get_bd_cells rst]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 zero
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {0}] [get_bd_cells zero]
create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 one
set_property -dict [list CONFIG.CONST_WIDTH {1} CONFIG.CONST_VAL {1}] [get_bd_cells one]
connect_bd_intf_net [get_bd_intf_pins ps/M_AXI_HPM0_FPD] [get_bd_intf_pins axi/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi/M00_AXI] [get_bd_intf_pins neural/S_AXI]
connect_bd_net [get_bd_pins ps/pl_clk0] [get_bd_pins ps/maxihpm0_fpd_aclk] \
    [get_bd_pins axi/aclk] [get_bd_pins neural/aclk] [get_bd_pins rst/slowest_sync_clk]
connect_bd_net [get_bd_pins ps/pl_resetn0] [get_bd_pins rst/ext_reset_in]
connect_bd_net [get_bd_pins zero/dout] [get_bd_pins rst/aux_reset_in] [get_bd_pins rst/mb_debug_sys_rst]
# No MMCM is present downstream. Constant lock assumes the PS releases its
# fabric reset after the provisional PL clock is stable; verify on the board.
connect_bd_net [get_bd_pins one/dout] [get_bd_pins rst/dcm_locked]
connect_bd_net [get_bd_pins rst/interconnect_aresetn] [get_bd_pins axi/aresetn]
connect_bd_net [get_bd_pins rst/peripheral_aresetn] [get_bd_pins neural/aresetn]

set segments [get_bd_addr_segs -quiet -of_objects [get_bd_intf_pins neural/S_AXI]]
if {[llength $segments] != 1} {error "Expected exactly one inferred neural register segment: $segments"}
# Exact 256-byte aperture matches the RTL's eight-bit byte address. The PS
# HPM0 window permits this address; occupancy in the real OS remains unknown.
assign_bd_address -target_address_space [get_bd_addr_spaces ps/Data] \
    -offset 0xA0000000 -range 0x100 [lindex $segments 0]

validate_bd_design
if {[get_property CONFIG.C_EXT_RESET_HIGH [get_bd_cells rst]] != 0} {
    error "Reset propagation did not select C_EXT_RESET_HIGH=0"
}
if {[get_property CONFIG.POLARITY [get_bd_pins rst/ext_reset_in]] ne "ACTIVE_LOW"} {
    error "External reset input did not propagate active-low polarity"
}
save_bd_design
write_bd_tcl -force [file join $output validated-candidate-ps-axi.tcl]
set report [open [file join $output candidate-properties.txt] w]
puts $report "scope=logical_candidate_only_pending_actual_board_image_compatibility"
puts $report "vivado=[version -short]"
puts $report "board_part=$board_part"
puts $report "part=$device"
puts $report "requested_clock_mhz=$requested_clock_mhz"
puts $report "derived_clock_hz=$clock_hz"
puts $report "board_file=$board_file"
puts $report "preset_file=$preset_file"
foreach cell {ps axi rst zero one neural} {
    puts $report "\nCELL $cell"
    puts $report [report_property -all -return_string [get_bd_cells $cell]]
}
foreach name {ps/M_AXI_HPM0_FPD axi/S00_AXI axi/M00_AXI neural/S_AXI} {
    puts $report "\nINTERFACE $name"
    puts $report [report_property -all -return_string [get_bd_intf_pins $name]]
}
foreach name {ps/pl_clk0 ps/pl_resetn0 rst/ext_reset_in rst/peripheral_aresetn neural/aclk neural/aresetn} {
    puts $report "\nPIN $name"
    puts $report [report_property -all -return_string [get_bd_pins $name]]
}
foreach segment [get_bd_addr_segs -quiet] {
    puts $report "\nADDRESS_SEGMENT $segment"
    puts $report [report_property -all -return_string $segment]
}
puts $report "\nEXTERNAL_PORTS [get_bd_ports -quiet]"
puts $report "EXTERNAL_INTERFACES [get_bd_intf_ports -quiet]"
close $report
if {[llength [get_bd_ports -quiet]] || [llength [get_bd_intf_ports -quiet]]} {
    error "Unexpected external ports; review before claiming a pin-free candidate"
}
puts "CANDIDATE_BOARD_PART=$board_part"
puts "CANDIDATE_PART=$device"
puts "CANDIDATE_PROPOSED_CLOCK_MHZ=$requested_clock_mhz"
puts "CANDIDATE_DERIVED_CLOCK_HZ=[get_property CONFIG.FREQ_HZ [get_bd_pins ps/pl_clk0]]"
puts "CANDIDATE_PROPOSED_MMIO_BASE=0xA0000000"
puts "CANDIDATE_PROPOSED_MMIO_RANGE=0x100"
puts "CANDIDATE_PROJECT=[file join $project_dir tiny_ps_axi_candidate.xpr]"
puts "PASS LOGICAL_PS_AXI_CANDIDATE_ONLY"
puts "NOT_A_BOARD_IMAGE_OR_BITSTREAM"
close_project
exit
