// Reuse one 32-term MAC across one, 32 or 96 output rows. No model values are hard-coded.
// Stored operands: 16 bits. Product: 32 bits. Accumulator: 48 bits.
// Q/K: scale 2^-26 -> 2^-11. V: scale 2^-27 -> 2^-12. All shift 15, ties even.
`timescale 1ns/1ps
module mac32 #(
    parameter integer ROWS = 1,
    parameter integer ROW_BITS = (ROWS > 1) ? $clog2(ROWS) : 1
) (
    input  logic clk,
    input  logic reset,
    input  logic load_valid,
    output logic load_ready,
    input  logic [4:0] load_address,
    input  logic [ROW_BITS-1:0] load_row,
    input  logic signed [15:0] load_input,
    input  logic signed [15:0] load_weight,
    input  logic start,
    output logic start_ready,
    output logic busy,
    output logic result_valid,
    input  logic result_ready,
    output logic signed [15:0] result,
    output logic [ROW_BITS-1:0] result_row,
    output logic saturated,
    output logic step_valid,
    output logic [4:0] step_index,
    output logic [ROW_BITS-1:0] step_row,
    output logic signed [15:0] step_input,
    output logic signed [15:0] step_weight,
    output logic signed [31:0] step_product,
    output logic signed [47:0] step_sum
);
    typedef enum logic [2:0] {IDLE, READ, MAC, ROUND, OUTPUT} state_t;
    state_t state;
    localparam integer WEIGHT_BITS = $clog2(ROWS*32);
    logic signed [15:0] input_memory [0:31];
    logic signed [15:0] weight_memory [0:ROWS*32-1];
    logic [ROW_BITS-1:0] row;
    logic [4:0] address;
    logic signed [15:0] operand_x, operand_w;
    logic signed [31:0] product;
    logic signed [47:0] accumulator, next_sum, rounded;

    assign busy = state != IDLE;
    assign load_ready = state == IDLE && !start && int'(load_row) < ROWS;
    assign start_ready = state == IDLE && !load_valid;
    assign result_valid = state == OUTPUT;
    assign result_row = row;
    assign product = operand_x * operand_w;
    assign next_sum = accumulator + {{16{product[31]}}, product};

    // Arithmetic shift gives the floor, including for negative numbers.
    // Low bits are the nonnegative remainder; increment on >half or odd ties.
    always_comb begin
        rounded = accumulator >>> 15;
        if (accumulator[14:0] > 15'h4000 ||
            (accumulator[14:0] == 15'h4000 && rounded[0]))
            rounded = rounded + 48'sd1;
    end

    always_ff @(posedge clk) begin
        if (!reset && load_valid && load_ready) begin
            if (load_row == 0) input_memory[load_address] <= load_input;
            weight_memory[WEIGHT_BITS'({load_row,load_address})] <= load_weight;
        end
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            address <= 5'd0;
            row <= '0;
            step_row <= '0;
            operand_x <= 16'sd0;
            operand_w <= 16'sd0;
            accumulator <= 48'sd0;
            result <= 16'sd0;
            saturated <= 1'b0;
            step_valid <= 1'b0;
            step_index <= 5'd0;
            step_input <= 16'sd0;
            step_weight <= 16'sd0;
            step_product <= 32'sd0;
            step_sum <= 48'sd0;
        end else begin
            step_valid <= 1'b0;
            case (state)
                IDLE: if (start && start_ready) begin
                    address <= 5'd0;
                    row <= '0;
                    accumulator <= 48'sd0;
                    saturated <= 1'b0;
                    state <= READ;
                end
                READ: begin
                    // Synchronous reads: consume these registers next cycle.
                    operand_x <= input_memory[address];
                    operand_w <= weight_memory[WEIGHT_BITS'({row,address})];
                    state <= MAC;
                end
                MAC: begin
                    accumulator <= next_sum;
                    step_valid <= 1'b1;
                    step_index <= address;
                    step_row <= row;
                    step_input <= operand_x;
                    step_weight <= operand_w;
                    step_product <= product;
                    step_sum <= next_sum;
                    if (address == 5'd31) state <= ROUND;
                    else begin
                        address <= address + 5'd1;
                        state <= READ;
                    end
                end
                ROUND: begin
                    if (rounded > 48'sd32767) begin
                        result <= 16'sh7fff;
                        saturated <= 1'b1;
                    end else if (rounded < -48'sd32768) begin
                        result <= 16'sh8000;
                        saturated <= 1'b1;
                    end else begin
                        result <= rounded[15:0];
                        saturated <= 1'b0;
                    end
                    state <= OUTPUT;
                end
                OUTPUT: if (result_ready) begin
                    if (int'(row) == ROWS-1) state <= IDLE;
                    else begin
                        row <= row + 1'b1;
                        address <= 5'd0;
                        accumulator <= 48'sd0;
                        saturated <= 1'b0;
                        state <= READ;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
