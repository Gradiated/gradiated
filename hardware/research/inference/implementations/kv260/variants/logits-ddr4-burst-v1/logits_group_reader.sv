// Eight 64-byte AXI reads supply one 512-byte, eight-lane logits group.
`timescale 1ns/1ps
module logits_group_reader #(
    parameter integer MAX_WAIT = 4096
) (
    input logic clk, reset, cancel, clear,
    input logic request,
    input logic [5:0] group_index,
    input logic [31:0] base,
    input logic read_pair,
    input logic [4:0] read_coordinate,
    output logic [127:0] weights,
    output logic valid, fault, busy,
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
    logic [2:0] burst, beat;
    logic [63:0] low [0:31], high [0:31];
    logic [4:0] coordinate;
    localparam integer TIMER_BITS = $clog2(MAX_WAIT+1);
    logic [TIMER_BITS-1:0] timer;
    logic bad_return, final_beat, deadline;

    assign busy = state != IDLE;
    assign arvalid = state == ADDRESS && !reset;
    assign rready = state == RESPONSE && !reset;
    assign ar_accept = arvalid && arready;
    assign r_accept = rready && rvalid;
    assign ar_blocked = arvalid && !arready && !discard && !cancel;
    assign r_wait = rready && !rvalid && !discard && !cancel;
    assign final_beat = beat == 3'd7;
    assign bad_return = rresp != 2'b00 || rid != 6'd0 || rlast != final_beat;
    assign deadline = timer == TIMER_BITS'(MAX_WAIT-1);
    assign coordinate = {burst,beat[2:1]};
    assign valid = r_accept && final_beat && burst == 3'd7 && !bad_return && !discard && !cancel;
    assign fault_event = !discard && !cancel &&
        ((r_accept && bad_return) || (deadline && (ar_blocked || r_wait)));

    // Coefficient order is coordinate major, then lane 0..7. Two physical
    // 64-bit banks take alternate beats and read in parallel into the MACs.
    always_ff @(posedge clk) begin
        if (r_accept && !discard && !cancel && !bad_return) begin
            if (beat[0]) high[coordinate] <= rdata;
            else low[coordinate] <= rdata;
        end
        if (read_pair && !reset) weights <= {high[read_coordinate],low[read_coordinate]};
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            araddr <= 0;
            burst <= 0;
            beat <= 0;
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
                    araddr <= {17'd0,base + {17'd0,group_index,9'd0}};
                    burst <= 0;
                    beat <= 0;
                    discard <= 0;
                    timer <= 0;
                    state <= ADDRESS;
                end
                ADDRESS: if (ar_accept) state <= RESPONSE;
                RESPONSE: if (r_accept && rid == 6'd0) begin
                    // Preserve an asserted AR, and drain only the currently
                    // issued burst after fault/cancel. Early RLAST is not
                    // sufficient to prove the declared burst has drained.
                    if (rlast && final_beat) begin
                        if (discard || cancel || bad_return || burst == 3'd7) state <= IDLE;
                        else begin
                            araddr <= araddr + 49'd64;
                            beat <= 0;
                            burst <= burst + 1'b1;
                            state <= ADDRESS;
                        end
                    end else if (!final_beat) beat <= beat + 1'b1;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
