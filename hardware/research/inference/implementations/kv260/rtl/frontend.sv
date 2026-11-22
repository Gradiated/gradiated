// Connected norm1-input -> Q/K/V -> Q/K RoPE -> committed Krot/V cache.
// Normalization and attention are separate stages, not implemented by this module.
// Queries stream only after the corresponding K/V token has been committed.
`timescale 1ns/1ps
module frontend (
    input logic clk, reset,
    input logic load_valid,
    output logic load_ready,
    input logic [4:0] load_address,
    input logic [6:0] load_row,
    input logic signed [15:0] load_input, load_weight,
    input logic coefficient_valid,
    output logic coefficient_ready,
    input logic [7:0] coefficient_position,
    input logic [2:0] coefficient_pair,
    input logic signed [15:0] load_cosine, load_sine,
    input logic start,
    input logic [8:0] token_position,
    output logic start_ready, busy,
    output logic query_valid,
    input logic query_ready,
    output logic [4:0] query_coordinate,
    output logic signed [15:0] query_value,
    output logic saturated,
    input logic read_valid,
    output logic read_ready,
    input logic [8:0] read_position,
    input logic [5:0] read_coordinate,
    output logic output_valid,
    input logic output_ready,
    output logic [7:0] output_position,
    output logic [4:0] output_coordinate,
    output logic signed [15:0] output_k, output_v,
    output logic [8:0] token_count
);
    typedef enum logic [3:0] {IDLE, PROJECT_START, PROJECT_WAIT, ROPE_LOAD,
        ROPE_START, ROPE_WAIT, APPEND, QUERY} state_t;
    state_t state;
    logic [8:0] position;
    logic [5:0] index;
    // Small interstage vectors. No CPU data substitution between these blocks.
    logic signed [15:0] qk_buffer [0:63], v_buffer [0:31];
    logic signed [15:0] rotated [0:63];
    logic mac_load_ready, mac_start_ready, mac_busy, mac_valid, mac_clip;
    logic [6:0] mac_row;
    logic signed [15:0] mac_result;
    logic mac_step_valid;
    logic [4:0] mac_step_index;
    logic [6:0] mac_step_row;
    logic signed [15:0] mac_step_input, mac_step_weight;
    logic signed [31:0] mac_step_product;
    logic signed [47:0] mac_step_sum;
    logic rope_load_ready, rope_coefficient_ready, rope_start_ready, rope_busy, rope_valid;
    logic [4:0] rope_pair;
    logic [5:0] rope_index_a, rope_index_b;
    logic signed [15:0] rope_a, rope_b;
    logic [1:0] rope_clip, rope_step_kind;
    logic rope_step_valid;
    logic [4:0] rope_step_pair;
    logic signed [15:0] rope_step_input, rope_step_coefficient;
    logic signed [31:0] rope_step_product;
    logic signed [47:0] rope_step_total;
    logic cache_write_ready, cache_read_ready, cache_output_valid, commit_valid;
    logic [4:0] next_coordinate;
    logic cache_read_valid;

    assign busy = state != IDLE;
    assign load_ready = !reset && state==IDLE && !coefficient_valid && !start && mac_load_ready;
    assign coefficient_ready = !reset && state==IDLE && !load_valid && !start && rope_coefficient_ready;
    // A held cache response must be consumed before starting another token.
    assign start_ready = !reset && state==IDLE && !load_valid && !coefficient_valid &&
                         !read_valid && !cache_output_valid && token_position==token_count &&
                         token_position<9'd256 && mac_start_ready;
    assign query_valid = !reset && state==QUERY;
    assign query_coordinate = index[4:0];
    assign query_value = rotated[index];
    assign cache_read_valid = read_valid && state==IDLE && !start && !reset;
    assign read_ready = state==IDLE && !start && cache_read_ready && !reset;
    assign output_valid = cache_output_valid;

    mac32 #(.ROWS(96)) projection (
        .clk(clk),.reset(reset),.load_valid(load_valid && load_ready),.load_ready(mac_load_ready),
        .load_address(load_address),.load_row(load_row),.load_input(load_input),.load_weight(load_weight),
        .start(state==PROJECT_START),.start_ready(mac_start_ready),.busy(mac_busy),
        .result_valid(mac_valid),.result_ready(state==PROJECT_WAIT),.result(mac_result),
        .result_row(mac_row),.saturated(mac_clip),.step_valid(mac_step_valid),
        .step_index(mac_step_index),.step_row(mac_step_row),.step_input(mac_step_input),
        .step_weight(mac_step_weight),.step_product(mac_step_product),.step_sum(mac_step_sum)
    );
    qk_rope rotation (
        .clk(clk),.reset(reset),.load_valid(state==ROPE_LOAD),.load_ready(rope_load_ready),
        .load_index(index),.load_value(qk_buffer[index]),
        .coefficient_valid(coefficient_valid && coefficient_ready),.coefficient_ready(rope_coefficient_ready),
        .coefficient_position(coefficient_position),.coefficient_pair(coefficient_pair),
        .load_cosine(load_cosine),.load_sine(load_sine),.start(state==ROPE_START),
        .token_position(position),.start_ready(rope_start_ready),.busy(rope_busy),
        .result_valid(rope_valid),.result_ready(state==ROPE_WAIT),.result_pair(rope_pair),
        .result_index_a(rope_index_a),.result_index_b(rope_index_b),.result_a(rope_a),.result_b(rope_b),
        .saturated(rope_clip),.step_valid(rope_step_valid),.step_kind(rope_step_kind),
        .step_pair(rope_step_pair),.step_input(rope_step_input),.step_coefficient(rope_step_coefficient),
        .step_product(rope_step_product),.step_total(rope_step_total)
    );
    kv_cache cache (
        .clk(clk),.reset(reset),.write_valid(state==APPEND),.write_ready(cache_write_ready),
        .write_position(position),.write_coordinate(index),.write_k(rotated[32+index]),.write_v(v_buffer[index]),
        .read_valid(cache_read_valid),.read_ready(cache_read_ready),.read_position(read_position),
        .read_coordinate(read_coordinate),.output_valid(cache_output_valid),.output_ready(output_ready),
        .output_position(output_position),.output_coordinate(output_coordinate),.output_k(output_k),
        .output_v(output_v),.token_count(token_count),.next_coordinate(next_coordinate),.commit_valid(commit_valid)
    );

    always_ff @(posedge clk) begin
        if (reset) begin
            state<=IDLE;position<=0;index<=0;saturated<=0;
        end else case (state)
            IDLE: if (start && start_ready) begin
                position<=token_position;index<=0;saturated<=0;state<=PROJECT_START;
            end
            PROJECT_START: if (mac_start_ready) state<=PROJECT_WAIT;
            PROJECT_WAIT: if (mac_valid) begin
                if (mac_row<64) qk_buffer[mac_row[5:0]]<=mac_result;
                else v_buffer[mac_row[4:0]]<=mac_result;
                saturated<=saturated || mac_clip;
                if (mac_row==95) begin index<=0;state<=ROPE_LOAD;end
            end
            ROPE_LOAD: if (rope_load_ready) begin
                if (index==63) begin index<=0;state<=ROPE_START;end
                else index<=index+1'b1;
            end
            ROPE_START: if (rope_start_ready) state<=ROPE_WAIT;
            ROPE_WAIT: if (rope_valid) begin
                rotated[rope_index_a]<=rope_a;rotated[rope_index_b]<=rope_b;
                saturated<=saturated || (|rope_clip);
                if (rope_pair==31) begin index<=0;state<=APPEND;end
            end
            APPEND: if (cache_write_ready) begin
                if (index==31) begin index<=0;state<=QUERY;end
                else index<=index+1'b1;
            end
            QUERY: if (query_ready) begin
                if (index==31) begin index<=0;state<=IDLE;end
                else index<=index+1'b1;
            end
            default: state<=IDLE;
        endcase
    end
endmodule
