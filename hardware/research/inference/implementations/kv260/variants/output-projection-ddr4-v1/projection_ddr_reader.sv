// One aligned 64-bit beat per signed 16-bit coefficient. Only the requested lane is used.
`timescale 1ns/1ps
module projection_ddr_reader #(
    parameter integer MAX_WAIT = 4096
) (
    input logic clk, reset, cancel, clear,
    input logic request,
    input logic [9:0] index,
    input logic [31:0] base,
    output logic valid, fault, busy,
    output logic signed [15:0] weight,
    output logic [48:0] araddr,
    output logic arvalid,
    input logic arready,
    input logic [63:0] rdata,
    input logic [5:0] rid,
    input logic [1:0] rresp,
    input logic rlast, rvalid,
    output logic rready,
    output logic ar_accept, r_accept, ar_blocked, r_wait, fault_event
);
    typedef enum logic [1:0] {IDLE, ADDRESS, RESPONSE} state_t;
    state_t state;
    logic discard;
    logic [1:0] lane;
    localparam integer TIMER_BITS = $clog2(MAX_WAIT+1);
    logic [TIMER_BITS-1:0] timer;
    logic bad_return, deadline;

    assign busy = state != IDLE;
    // A software cancel leaves ARVALID asserted until ARREADY and consumes
    // all R beats through RLAST. Only shared fabric reset can drop either.
    assign arvalid = state == ADDRESS && !reset;
    assign rready = state == RESPONSE && !reset;
    assign ar_accept = arvalid && arready;
    assign r_accept = rready && rvalid;
    assign ar_blocked = arvalid && !arready && !discard && !cancel;
    assign r_wait = rready && !rvalid && !discard && !cancel;
    assign bad_return = rresp != 2'b00 || rid != 6'd0 || !rlast;
    assign deadline = timer == TIMER_BITS'(MAX_WAIT-1);
    assign valid = r_accept && !bad_return && !discard && !cancel;
    assign fault_event = !discard && !cancel &&
        ((r_accept && bad_return) || (deadline && (ar_blocked || r_wait)));
    assign weight = $signed(rdata[{lane,4'b0000} +: 16]);

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            araddr <= 0;
            lane <= 0;
            discard <= 0;
            fault <= 0;
            timer <= 0;
        end else begin
            if (clear || cancel) fault <= 0;
            else if (fault_event) fault <= 1;
            if (fault_event || cancel) discard <= 1;
            if ((ar_blocked || r_wait) && !deadline) timer <= timer + 1'b1;
            case (state)
                IDLE: if (request && !fault && !cancel) begin
                    araddr <= {17'd0, base + {21'd0,index[9:2],3'd0}};
                    lane <= index[1:0];
                    discard <= 0;
                    timer <= 0;
                    state <= ADDRESS;
                end
                ADDRESS: if (ar_accept) state <= RESPONSE;
                RESPONSE: if (r_accept && rlast) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
