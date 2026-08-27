`timescale 1ns/1ps

module kda_axi_top #(
    parameter integer HEAD_DIM = 128,
    parameter integer LANES = 16
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 99999001" *)
    input  wire         s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME s_axi_aresetn, POLARITY ACTIVE_LOW" *)
    input  wire         s_axi_aresetn,

    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWADDR" *)
    (* X_INTERFACE_PARAMETER = "XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 16, FREQ_HZ 99999001, HAS_BURST 0, HAS_LOCK 0, HAS_PROT 1, HAS_CACHE 0, HAS_QOS 0, HAS_REGION 0, SUPPORTS_NARROW_BURST 0, NUM_READ_OUTSTANDING 1, NUM_WRITE_OUTSTANDING 1" *)
    input  wire [15:0]  s_axi_awaddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input wire [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input wire s_axi_awvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output reg s_axi_awready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input wire [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input wire [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input wire s_axi_wvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output reg s_axi_wready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output wire [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output reg s_axi_bvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input wire s_axi_bready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input wire [15:0] s_axi_araddr,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input wire [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input wire s_axi_arvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output reg s_axi_arready,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output reg [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output wire [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output reg s_axi_rvalid,
    (* X_INTERFACE_INFO = "xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input wire s_axi_rready
);
    localparam [15:0] REG_ID = 16'h0000;
    localparam [15:0] REG_CONTROL = 16'h0004;
    localparam [15:0] REG_STATUS = 16'h0008;
    localparam [15:0] REG_CYCLES = 16'h000c;
    localparam [15:0] REG_HEAD_DIM = 16'h0010;
    localparam [15:0] REG_LANES = 16'h0014;
    localparam [15:0] REG_BETA = 16'h0018;
    localparam [15:0] Q_BASE = 16'h1000;
    localparam [15:0] K_BASE = 16'h1400;
    localparam [15:0] V_BASE = 16'h1800;
    localparam [15:0] ALPHA_BASE = 16'h1c00;
    localparam [15:0] OUTPUT_BASE = 16'h2000;

    reg aw_pending;
    reg w_pending;
    reg read_pending;
    reg [15:0] awaddr_latched;
    reg [31:0] wdata_latched;
    reg [3:0] wstrb_latched;
    reg [15:0] araddr_latched;

    reg start_pulse;
    reg clear_pulse;
    reg cfg_wr_en;
    reg [2:0] cfg_wr_kind;
    reg [15:0] cfg_wr_addr;
    reg [31:0] cfg_wr_data;
    reg [15:0] out_rd_addr;
    wire [31:0] out_rd_data;
    wire core_busy;
    wire core_done;
    wire [31:0] core_cycles;

    wire unused_inputs;
    assign unused_inputs = ^{s_axi_awprot, s_axi_arprot};
    assign s_axi_bresp = 2'b00;
    assign s_axi_rresp = 2'b00;

    kda_core #(
        .HEAD_DIM(HEAD_DIM),
        .LANES(LANES)
    ) core (
        .clk(s_axi_aclk),
        .rst_n(s_axi_aresetn),
        .start(start_pulse),
        .clear_state(clear_pulse),
        .cfg_wr_en(cfg_wr_en),
        .cfg_wr_kind(cfg_wr_kind),
        .cfg_wr_addr(cfg_wr_addr),
        .cfg_wr_data(cfg_wr_data),
        .out_rd_addr(out_rd_addr),
        .out_rd_data(out_rd_data),
        .busy(core_busy),
        .done(core_done),
        .cycles(core_cycles)
    );

    always @(posedge s_axi_aclk) begin
        if (!s_axi_aresetn) begin
            s_axi_awready <= 1'b0;
            s_axi_wready <= 1'b0;
            s_axi_bvalid <= 1'b0;
            s_axi_arready <= 1'b0;
            s_axi_rvalid <= 1'b0;
            s_axi_rdata <= 32'd0;
            aw_pending <= 1'b0;
            w_pending <= 1'b0;
            read_pending <= 1'b0;
            awaddr_latched <= 16'd0;
            wdata_latched <= 32'd0;
            wstrb_latched <= 4'd0;
            araddr_latched <= 16'd0;
            start_pulse <= 1'b0;
            clear_pulse <= 1'b0;
            cfg_wr_en <= 1'b0;
            cfg_wr_kind <= 3'd0;
            cfg_wr_addr <= 16'd0;
            cfg_wr_data <= 32'd0;
            out_rd_addr <= 16'd0;
        end else begin
            s_axi_awready <= 1'b0;
            s_axi_wready <= 1'b0;
            s_axi_arready <= 1'b0;
            start_pulse <= 1'b0;
            clear_pulse <= 1'b0;
            cfg_wr_en <= 1'b0;

            if (!aw_pending && !s_axi_bvalid && s_axi_awvalid) begin
                awaddr_latched <= s_axi_awaddr;
                aw_pending <= 1'b1;
                s_axi_awready <= 1'b1;
            end
            if (!w_pending && !s_axi_bvalid && s_axi_wvalid) begin
                wdata_latched <= s_axi_wdata;
                wstrb_latched <= s_axi_wstrb;
                w_pending <= 1'b1;
                s_axi_wready <= 1'b1;
            end

            if (aw_pending && w_pending && !s_axi_bvalid) begin
                aw_pending <= 1'b0;
                w_pending <= 1'b0;
                s_axi_bvalid <= 1'b1;
                if (|wstrb_latched) begin
                    if (awaddr_latched == REG_CONTROL) begin
                        start_pulse <= wdata_latched[0];
                        clear_pulse <= wdata_latched[1];
                    end else if (awaddr_latched == REG_BETA) begin
                        cfg_wr_en <= 1'b1;
                        cfg_wr_kind <= 3'd4;
                        cfg_wr_addr <= 16'd0;
                        cfg_wr_data <= wdata_latched;
                    end else if (awaddr_latched >= Q_BASE && awaddr_latched < Q_BASE + HEAD_DIM * 4) begin
                        cfg_wr_en <= 1'b1;
                        cfg_wr_kind <= 3'd0;
                        cfg_wr_addr <= (awaddr_latched - Q_BASE) >> 2;
                        cfg_wr_data <= wdata_latched;
                    end else if (awaddr_latched >= K_BASE && awaddr_latched < K_BASE + HEAD_DIM * 4) begin
                        cfg_wr_en <= 1'b1;
                        cfg_wr_kind <= 3'd1;
                        cfg_wr_addr <= (awaddr_latched - K_BASE) >> 2;
                        cfg_wr_data <= wdata_latched;
                    end else if (awaddr_latched >= V_BASE && awaddr_latched < V_BASE + HEAD_DIM * 4) begin
                        cfg_wr_en <= 1'b1;
                        cfg_wr_kind <= 3'd2;
                        cfg_wr_addr <= (awaddr_latched - V_BASE) >> 2;
                        cfg_wr_data <= wdata_latched;
                    end else if (awaddr_latched >= ALPHA_BASE && awaddr_latched < ALPHA_BASE + HEAD_DIM * 4) begin
                        cfg_wr_en <= 1'b1;
                        cfg_wr_kind <= 3'd3;
                        cfg_wr_addr <= (awaddr_latched - ALPHA_BASE) >> 2;
                        cfg_wr_data <= wdata_latched;
                    end
                end
            end
            if (s_axi_bvalid && s_axi_bready)
                s_axi_bvalid <= 1'b0;

            if (!read_pending && !s_axi_rvalid && s_axi_arvalid) begin
                araddr_latched <= s_axi_araddr;
                read_pending <= 1'b1;
                s_axi_arready <= 1'b1;
                if (s_axi_araddr >= OUTPUT_BASE && s_axi_araddr < OUTPUT_BASE + HEAD_DIM * 4)
                    out_rd_addr <= (s_axi_araddr - OUTPUT_BASE) >> 2;
            end else if (read_pending && !s_axi_rvalid) begin
                read_pending <= 1'b0;
                s_axi_rvalid <= 1'b1;
                case (araddr_latched)
                    REG_ID: s_axi_rdata <= 32'h4b444131;
                    REG_STATUS: s_axi_rdata <= {30'd0, core_done, core_busy};
                    REG_CYCLES: s_axi_rdata <= core_cycles;
                    REG_HEAD_DIM: s_axi_rdata <= HEAD_DIM;
                    REG_LANES: s_axi_rdata <= LANES;
                    default: begin
                        if (araddr_latched >= OUTPUT_BASE && araddr_latched < OUTPUT_BASE + HEAD_DIM * 4)
                            s_axi_rdata <= out_rd_data;
                        else
                            s_axi_rdata <= 32'd0;
                    end
                endcase
            end
            if (s_axi_rvalid && s_axi_rready)
                s_axi_rvalid <= 1'b0;
        end
    end
endmodule
