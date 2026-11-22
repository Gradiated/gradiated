// Thin AXI4-Lite transport around the neural RTL core. No neural math is moved
// to the host. AXI reads/writes each have at most one outstanding response.
// Status0x00: configured,busy,error,saturated,logit_valid in bits0..4;
// bit5 generic token capacity, bit6 generic model-load capacity (not native READY).
// Bank0x04 and address0x08 are RW. Data0x0c pushes a model word; token0x10
// pushes a token. Index0x14 peeks; data0x18 consumes only on RVALID&RREADY.
// Control0x1c: 1=idle context clear, 2=core reset/full reload, 0=no-op.
// Context count0x20 is read-only, unsigned9 including the full count256.
`timescale 1ns/1ps
module axi_transformer (
    (* X_INTERFACE_INFO="xilinx.com:signal:clock:1.0 aclk CLK",
       X_INTERFACE_PARAMETER="XIL_INTERFACENAME aclk, ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET aresetn" *)
    input logic aclk,
    (* X_INTERFACE_INFO="xilinx.com:signal:reset:1.0 aresetn RST",
       X_INTERFACE_PARAMETER="XIL_INTERFACENAME aresetn, POLARITY ACTIVE_LOW" *)
    input logic aresetn,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWADDR",
       X_INTERFACE_PARAMETER="XIL_INTERFACENAME S_AXI, PROTOCOL AXI4LITE, DATA_WIDTH 32, ADDR_WIDTH 8" *)
    input logic [7:0] s_axi_awaddr,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWPROT" *) input logic [2:0] s_axi_awprot,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWVALID" *) input logic s_axi_awvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI AWREADY" *) output logic s_axi_awready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WDATA" *) input logic [31:0] s_axi_wdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WSTRB" *) input logic [3:0] s_axi_wstrb,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WVALID" *) input logic s_axi_wvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI WREADY" *) output logic s_axi_wready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BRESP" *) output logic [1:0] s_axi_bresp,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BVALID" *) output logic s_axi_bvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI BREADY" *) input logic s_axi_bready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARADDR" *) input logic [7:0] s_axi_araddr,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARPROT" *) input logic [2:0] s_axi_arprot,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARVALID" *) input logic s_axi_arvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI ARREADY" *) output logic s_axi_arready,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RDATA" *) output logic [31:0] s_axi_rdata,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RRESP" *) output logic [1:0] s_axi_rresp,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RVALID" *) output logic s_axi_rvalid,
    (* X_INTERFACE_INFO="xilinx.com:interface:aximm:1.0 S_AXI RREADY" *) input logic s_axi_rready
);
    localparam logic [1:0] OKAY=2'b00,SLVERR=2'b10;
    logic have_aw,have_w;
    logic [7:0] write_address;
    logic [31:0] write_data;
    logic [3:0] write_strobe;
    logic [3:0] model_bank;
    logic [15:0] model_address;
    logic write_execute,write_ok,model_push,token_push,clear_pulse,reset_pulse,soft_reset;
    logic read_holds_logit,read_claims_logit;
    logic core_weight_ready,core_configured,core_token_ready,core_busy,core_logit_valid;
    logic core_saturated,core_error;
    logic [8:0] core_logit_index,core_context_count;
    logic signed [31:0] core_logit;
    logic [4:0] core_phase;

    assign s_axi_awready=aresetn && !have_aw && !s_axi_bvalid && !soft_reset;
    assign s_axi_wready=aresetn && !have_w && !s_axi_bvalid && !soft_reset;
    assign s_axi_arready=aresetn && !s_axi_rvalid && !soft_reset;
    assign write_execute=aresetn && have_aw && have_w && !s_axi_bvalid && !soft_reset;
    // The command wires are asserted for exactly the write execution edge.
    assign model_push=write_execute && write_address==8'h0c && write_strobe==4'hf;
    assign token_push=write_execute && write_address==8'h10 && write_strobe==4'hf && write_data[31:9]==0 &&
                      write_data[8:0]<320;
    assign clear_pulse=write_execute && write_address==8'h1c && write_strobe==4'hf && write_data==1 &&
                       !core_busy && !read_holds_logit && !read_claims_logit;
    assign read_claims_logit=aresetn && s_axi_arvalid && s_axi_arready && s_axi_araddr==8'h18 && core_logit_valid && !core_error;
    assign reset_pulse=write_execute && write_address==8'h1c && write_strobe==4'hf && write_data==2 &&
                       !read_holds_logit && !read_claims_logit;

    always_comb begin
        write_ok=0;
        if(write_address[1:0]==0 && write_strobe==4'hf)begin
            case(write_address)
                8'h04:write_ok=write_data[31:4]==0 && write_data[3:0]<15 && write_data[3:0]!=12;
                8'h08:write_ok=write_data[31:16]==0;
                8'h0c:write_ok=core_weight_ready;
                8'h10:write_ok=write_data[31:9]==0 && write_data[8:0]<320 && core_token_ready;
                8'h1c:write_ok=write_data==0 || clear_pulse || reset_pulse;
                default:write_ok=0;
            endcase
        end
    end

    transformer core (
        .clk(aclk),.reset(!aresetn || soft_reset),
        .weight_valid(model_push),.weight_ready(core_weight_ready),.weight_bank(model_bank),
        .weight_address(model_address),.weight_value(write_data),.configured(core_configured),
        .clear_context(clear_pulse),.token_valid(token_push),.token_ready(core_token_ready),.token(write_data[8:0]),
        .busy(core_busy),.logit_valid(core_logit_valid),
        .logit_ready(aresetn && s_axi_rvalid && s_axi_rready && read_holds_logit && !core_error && !soft_reset),
        .logit_index(core_logit_index),.logit(core_logit),.saturated(core_saturated),.error(core_error),
        .context_count(core_context_count),.phase(core_phase)
    );

    always_ff @(posedge aclk) begin
        if(!aresetn)begin
            have_aw<=0;have_w<=0;write_address<=0;write_data<=0;write_strobe<=0;
            model_bank<=0;model_address<=0;soft_reset<=0;read_holds_logit<=0;
            s_axi_bvalid<=0;s_axi_bresp<=OKAY;s_axi_rvalid<=0;s_axi_rresp<=OKAY;s_axi_rdata<=0;
        end else begin
            soft_reset<=0;
            if(s_axi_awvalid && s_axi_awready)begin have_aw<=1;write_address<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready)begin have_w<=1;write_data<=s_axi_wdata;write_strobe<=s_axi_wstrb;end
            if(s_axi_bvalid && s_axi_bready)s_axi_bvalid<=0;
            if(write_execute)begin
                have_aw<=0;have_w<=0;s_axi_bvalid<=1;s_axi_bresp<=write_ok ? OKAY:SLVERR;
                if(write_ok)begin
                    if(write_address==8'h04)model_bank<=write_data[3:0];
                    if(write_address==8'h08)model_address<=write_data[15:0];
                    if(model_push && core_weight_ready)model_address<=model_address+16'd1;
                    if(reset_pulse)begin soft_reset<=1;model_bank<=0;model_address<=0;end
                end
            end
            if(s_axi_rvalid && s_axi_rready)begin s_axi_rvalid<=0;read_holds_logit<=0;end
            if(s_axi_arvalid && s_axi_arready)begin
                s_axi_rvalid<=1;s_axi_rresp<=OKAY;s_axi_rdata<=0;read_holds_logit<=0;
                if(s_axi_araddr[1:0]!=0)s_axi_rresp<=SLVERR;
                else case(s_axi_araddr)
                    8'h00:s_axi_rdata<={25'd0,
                        (!core_configured && !core_busy && !soft_reset),
                        (core_configured && !core_busy && !core_error && core_context_count<256 && !soft_reset),
                        core_logit_valid,core_saturated,core_error,core_busy,core_configured};
                    8'h04:s_axi_rdata<={28'd0,model_bank};
                    8'h08:s_axi_rdata<={16'd0,model_address};
                    8'h14:s_axi_rdata<={23'd0,core_logit_index};
                    8'h18:begin
                        if(core_logit_valid && !core_error)begin s_axi_rdata<=core_logit;read_holds_logit<=1;end
                        else s_axi_rresp<=SLVERR;
                    end
                    8'h20:s_axi_rdata<={23'd0,core_context_count};
                    default:s_axi_rresp<=SLVERR;
                endcase
            end
        end
    end
endmodule
