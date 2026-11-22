// Read one scalar operand, one four-weight beat, or one aligned 32-weight row.
// The projection owns the only command port and requests operands in row order.
`timescale 1ns/1ps
module projection_ddr_reader #(
    parameter integer MAX_WAIT = 4096
) (
    input logic clk, reset, cancel, clear,
    input logic request,
    input logic [9:0] index,
    input logic [31:0] base,
    input logic [1:0] mode,
    output logic valid, fault, busy,
    output logic signed [15:0] weight,
    output logic [48:0] araddr,
    output logic [7:0] arlen,
    output logic arvalid,
    input logic arready,
    input logic [63:0] rdata,
    input logic [5:0] rid,
    input logic [1:0] rresp,
    input logic rlast, rvalid,
    output logic rready,
    output logic ar_accept, r_accept, ar_blocked, r_wait, fault_event
);
    localparam logic [1:0] SCALAR = 2'd1, BEAT = 2'd2, ROW = 2'd3;
    typedef enum logic [1:0] {IDLE, ADDRESS, RESPONSE} state_t;
    state_t state;
    logic discard, buffered, buffer_hit, last_weight;
    logic [1:0] active_mode;
    logic [9:0] group_base, saved_group;
    logic [2:0] beat;
    logic [63:0] row_data [0:7];
    logic [63:0] selected_beat;
    localparam integer TIMER_BITS = $clog2(MAX_WAIT+1);
    logic [TIMER_BITS-1:0] timer;
    logic bad_return, final_beat, usable_return, deadline;

    assign group_base = mode == ROW ? {index[9:5],5'd0} : {index[9:2],2'd0};
    assign buffer_hit = buffered && group_base == saved_group && mode == active_mode;
    assign last_weight = mode == ROW ? (&index[4:0]) : (&index[1:0]);
    assign busy = state != IDLE;

    // Cancel invalidates buffered data and cancels calculation. It must not
    // change a pending address or stop draining a response before RLAST.
    assign arvalid = state == ADDRESS && !reset;
    assign rready = state == RESPONSE && !reset;
    assign ar_accept = arvalid && arready;
    assign r_accept = rready && rvalid;
    assign ar_blocked = arvalid && !arready && !discard && !cancel;
    assign r_wait = rready && !rvalid && !discard && !cancel;
    assign final_beat = {5'd0,beat} == arlen;
    assign bad_return = rresp != 2'b00 || rid != 6'd0 || rlast != final_beat;
    assign deadline = timer == TIMER_BITS'(MAX_WAIT-1);
    assign usable_return = r_accept && final_beat && !bad_return && !discard;
    assign valid = request && !cancel && !fault && (buffer_hit || usable_return);
    assign fault_event = !discard && !cancel &&
        ((r_accept && bad_return) || (deadline && (ar_blocked || r_wait)));

    // A row becomes usable on its final beat. Its first coefficient can be
    // captured on that edge, so there is no extra buffer-read setup clock.
    always_comb begin
        if (buffer_hit) selected_beat = row_data[mode == ROW ? index[4:2] : 3'd0];
        else if (active_mode == ROW) selected_beat = row_data[0];
        else selected_beat = rdata;
    end
    assign weight = $signed(selected_beat[{index[1:0],4'b0000} +: 16]);

    always_ff @(posedge clk) begin
        if (r_accept && !discard && !cancel && !bad_return && active_mode != SCALAR)
            row_data[beat] <= rdata;
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            araddr <= 0;
            arlen <= 0;
            beat <= 0;
            active_mode <= 0;
            saved_group <= 0;
            buffered <= 0;
            discard <= 0;
            fault <= 0;
            timer <= 0;
        end else begin
            if (clear || cancel) fault <= 0;
            else if (fault_event) fault <= 1;
            if (fault_event || cancel) discard <= 1;
            if (cancel || clear || fault_event || (buffer_hit && valid && last_weight))
                buffered <= 0;
            else if (request && usable_return && !discard && !cancel && active_mode != SCALAR)
                buffered <= 1;
            if ((ar_blocked || r_wait) && !deadline) timer <= timer + 1'b1;
            case (state)
                IDLE: if (request && !buffer_hit && !fault && !cancel) begin
                    araddr <= {17'd0, base + {21'd0,group_base,1'b0}};
                    arlen <= mode == ROW ? 8'd7 : 8'd0;
                    active_mode <= mode;
                    saved_group <= group_base;
                    buffered <= 0;
                    beat <= 0;
                    discard <= 0;
                    timer <= 0;
                    state <= ADDRESS;
                end
                ADDRESS: if (ar_accept) state <= RESPONSE;
                RESPONSE: if (r_accept && rid == 6'd0) begin
                    // A premature RLAST cannot prove that the declared burst
                    // has drained. Keep ownership until its declared length
                    // and a matching-ID RLAST have both been observed.
                    if (rlast && final_beat) state <= IDLE;
                    else if (!final_beat) beat <= beat + 1'b1;
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
