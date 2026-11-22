// Serial dense projection, including 128-term down and 320-row tied output head.
// One signed16 x signed16 multiplier, signed48 sum, one final RNE/clipping step.
// Stored matrices have output-row x input-coordinate order; no model values here.
`timescale 1ns/1ps
module dense #(
    parameter integer INPUTS = 32,
    parameter integer OUTPUTS = 32,
    parameter integer SHIFT = 15,
    parameter integer RESULT_BITS = 16
) (
    input logic clk, reset,
    input logic input_valid,
    output logic input_ready,
    input logic [7:0] input_address,
    input logic signed [15:0] input_value,
    input logic weight_valid,
    output logic weight_ready,
    input logic [8:0] weight_row,
    input logic [7:0] weight_address,
    input logic signed [15:0] weight_value,
    input logic start,
    output logic start_ready, busy,
    output logic result_valid,
    input logic result_ready,
    output logic signed [RESULT_BITS-1:0] result,
    output logic [8:0] result_row,
    output logic saturated,
    output logic step_valid,
    output logic [7:0] step_index,
    output logic [8:0] step_row,
    output logic signed [15:0] step_input, step_weight,
    output logic signed [31:0] step_product,
    output logic signed [47:0] step_sum
);
    localparam integer INPUT_BITS = (INPUTS > 1) ? $clog2(INPUTS) : 1;
    localparam integer ROW_BITS = (OUTPUTS > 1) ? $clog2(OUTPUTS) : 1;
    localparam integer WEIGHT_BITS = (INPUTS*OUTPUTS > 1) ? $clog2(INPUTS*OUTPUTS) : 1;
    localparam logic signed [47:0] RESULT_MAX = (48'sd1 << (RESULT_BITS-1))-48'sd1;
    localparam logic signed [47:0] RESULT_MIN = -(48'sd1 << (RESULT_BITS-1));
    typedef enum logic [2:0] {IDLE, READ, MAC, ROUND, OUTPUT} state_t;
    state_t state;
    logic signed [15:0] input_memory [0:INPUTS-1];
    logic signed [15:0] weight_memory [0:INPUTS*OUTPUTS-1];
    logic [INPUT_BITS-1:0] address;
    logic [ROW_BITS-1:0] row;
    logic signed [15:0] operand_x, operand_w;
    // Preserve the shared product net: otherwise synthesis may duplicate its
    // multiplier to expose step_product while also fusing multiply+sum in a DSP.
    (* keep = "true", use_dsp = "yes" *) logic signed [31:0] product;
    logic signed [47:0] accumulator, rounded;
    (* use_dsp = "no" *) logic signed [47:0] next_sum;
    logic [WEIGHT_BITS-1:0] read_weight_address, write_weight_address;

    // Validate full external indices before narrowing to actual memory addresses.
    assign input_ready = state == IDLE && !start && int'(input_address) < INPUTS;
    assign weight_ready = state == IDLE && !start && int'(weight_row) < OUTPUTS &&
                          int'(weight_address) < INPUTS;
    assign start_ready = state == IDLE && !input_valid && !weight_valid;
    assign busy = state != IDLE;
    assign result_valid = state == OUTPUT;
    assign result_row = 9'(row);
    assign read_weight_address = WEIGHT_BITS'(int'(row)*INPUTS+int'(address));
    assign write_weight_address = WEIGHT_BITS'(int'(weight_row)*INPUTS+int'(weight_address));
    assign product = operand_x * operand_w;
    assign next_sum = accumulator + {{16{product[31]}},product};

    generate
        if (SHIFT == 0) begin : no_shift
            assign rounded = accumulator;
        end else begin : round_shift
            always_comb begin
                rounded = accumulator >>> SHIFT;
                if (accumulator[SHIFT-1:0] > (SHIFT'(1) << (SHIFT-1)) ||
                    (accumulator[SHIFT-1:0] == (SHIFT'(1) << (SHIFT-1)) && rounded[0]))
                    rounded = rounded + 48'sd1;
            end
        end
    endgenerate

    // Neither reset nor a cancelled calculation erases model/input RAM bits.
    always_ff @(posedge clk) begin
        if (!reset && input_valid && input_ready)
            input_memory[INPUT_BITS'(input_address)] <= input_value;
        if (!reset && weight_valid && weight_ready)
            weight_memory[write_weight_address] <= weight_value;
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE; address <= 0; row <= 0;
            operand_x <= 0; operand_w <= 0; accumulator <= 0;
            result <= 0; saturated <= 0;
            step_valid <= 0; step_index <= 0; step_row <= 0;
            step_input <= 0; step_weight <= 0; step_product <= 0; step_sum <= 0;
        end else begin
            step_valid <= 0;
            case (state)
                IDLE: if (start && start_ready) begin
                    row <= 0; address <= 0; accumulator <= 0; saturated <= 0;
                    state <= READ;
                end
                READ: begin
                    operand_x <= input_memory[address];
                    operand_w <= weight_memory[read_weight_address];
                    state <= MAC;
                end
                MAC: begin
                    accumulator <= next_sum;
                    step_valid <= 1; step_index <= 8'(address); step_row <= 9'(row);
                    step_input <= operand_x; step_weight <= operand_w;
                    step_product <= product; step_sum <= next_sum;
                    if (int'(address) == INPUTS-1) state <= ROUND;
                    else begin address <= address + 1'b1; state <= READ; end
                end
                ROUND: begin
                    if (rounded > RESULT_MAX) begin result <= RESULT_BITS'(RESULT_MAX); saturated <= 1; end
                    else if (rounded < RESULT_MIN) begin result <= RESULT_BITS'(RESULT_MIN); saturated <= 1; end
                    else begin result <= RESULT_BITS'(rounded); saturated <= 0; end
                    state <= OUTPUT;
                end
                OUTPUT: if (result_ready) begin
                    if (int'(row) == OUTPUTS-1) state <= IDLE;
                    else begin
                        row <= row + 1'b1; address <= 0; accumulator <= 0; saturated <= 0;
                        state <= READ;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
