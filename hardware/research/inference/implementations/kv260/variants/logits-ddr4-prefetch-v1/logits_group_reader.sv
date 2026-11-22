// Eight 64-byte AXI reads supply each 512-byte, eight-lane logits group.
// Two slots let the next group fill while the current group is consumed.
`timescale 1ns/1ps
module logits_group_reader #(
    parameter integer MAX_WAIT = 4096
) (
    input logic clk, reset, cancel, clear,
    input logic request, // A score invocation is active.
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
    // A group is published only after the entire successful burst sequence.
    // The next fetch can be at most one group ahead of the score consumer.
    localparam logic [5:0] GROUP_COUNT = 6'd40;
    logic [5:0] next_fetch_group;
    logic start_fetch, complete_group;
    logic [5:0] write_coordinate, read_address;
    logic [63:0] low [0:63], high [0:63];
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
    assign start_fetch = state == IDLE && request && !fault && !cancel &&
        next_fetch_group < GROUP_COUNT &&
        (next_fetch_group == group_index || next_fetch_group == group_index + 6'd1);
    assign complete_group = r_accept && final_beat && burst == 3'd7 &&
        !bad_return && !discard && !cancel && request;
    assign write_coordinate = {next_fetch_group[0],burst,beat[2:1]};
    assign read_address = {group_index[0],read_coordinate};
    // A group completing on the PRIME edge can provide coordinate zero:
    // the final beat writes coordinate 31, a different buffer address.
    assign valid = request && !fault && !cancel &&
        (next_fetch_group > group_index || (complete_group && next_fetch_group == group_index));
    assign fault_event = !discard && !cancel &&
        ((r_accept && bad_return) || (deadline && (ar_blocked || r_wait)));

    // The high address bit selects the group slot. Alternate beats write
    // the two 64-bit halves, and the MACs read the halves in parallel.
    always_ff @(posedge clk) begin
        if (r_accept && !discard && !cancel && !bad_return && request) begin
            if (beat[0]) high[write_coordinate] <= rdata;
            else low[write_coordinate] <= rdata;
        end
        if (read_pair && !reset && valid) weights <= {high[read_address],low[read_address]};
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
            next_fetch_group <= 0;
        end else begin
            if (!request || cancel || fault_event) next_fetch_group <= 0;
            else if (complete_group) next_fetch_group <= next_fetch_group + 1'b1;
            if (clear || cancel) fault <= 0;
            else if (fault_event) fault <= 1;
            if (fault_event || cancel) discard <= 1;
            if ((ar_blocked || r_wait) && !deadline) timer <= timer + 1'b1;
            case (state)
                IDLE: if (start_fetch) begin
                    araddr <= {17'd0,base + {17'd0,next_fetch_group,9'd0}};
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
