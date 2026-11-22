// Selected split-half RoPE: Q/K, two heads of 16, pairs (j,j+8).
// One serial multiplier; four products per pair. No network answers are stored.
`timescale 1ns/1ps
module qk_rope (
    input logic clk, reset,
    input logic load_valid,
    output logic load_ready,
    input logic [5:0] load_index,
    input logic signed [15:0] load_value,
    input logic coefficient_valid,
    output logic coefficient_ready,
    input logic [7:0] coefficient_position,
    input logic [2:0] coefficient_pair,
    input logic signed [15:0] load_cosine, load_sine,
    input logic start,
    input logic [8:0] token_position,
    output logic start_ready, busy, result_valid,
    input logic result_ready,
    output logic [4:0] result_pair,
    output logic [5:0] result_index_a, result_index_b,
    output logic signed [15:0] result_a, result_b,
    output logic [1:0] saturated,
    output logic step_valid,
    output logic [1:0] step_kind,
    output logic [4:0] step_pair,
    output logic signed [15:0] step_input, step_coefficient,
    output logic signed [31:0] step_product,
    output logic signed [47:0] step_total
);
    typedef enum logic [2:0] {IDLE, READ, MUL_AC, MUL_BS, MUL_BC, MUL_AS, ROUND, OUTPUT} state_t;
    state_t state;
    logic signed [15:0] input_memory [0:63];
    logic signed [15:0] cosine_memory [0:2047], sine_memory [0:2047];
    logic [7:0] position;
    logic [4:0] pair_index;
    logic signed [15:0] a, b, cosine, sine, operand, coefficient;
    logic signed [31:0] product;
    logic signed [47:0] wide_product, combined_a, combined_b, rounded_a, rounded_b;
    logic [10:0] coefficient_address;

    assign load_ready = state == IDLE && !start && !coefficient_valid;
    assign coefficient_ready = state == IDLE && !start && !load_valid;
    assign start_ready = state == IDLE && !load_valid && !coefficient_valid && token_position < 9'd256;
    assign busy = state != IDLE;
    assign result_valid = state == OUTPUT;
    assign result_pair = pair_index;
    assign result_index_a = {pair_index[4:3], 1'b0, pair_index[2:0]};
    assign result_index_b = {pair_index[4:3], 1'b1, pair_index[2:0]};
    assign coefficient_address = {position, pair_index[2:0]};
    always_comb begin
        operand = 16'sd0; coefficient = 16'sd0;
        case (state)
            MUL_AC: begin operand = a; coefficient = cosine; end
            MUL_BS: begin operand = b; coefficient = sine; end
            MUL_BC: begin operand = b; coefficient = cosine; end
            MUL_AS: begin operand = a; coefficient = sine; end
            default: begin end
        endcase
    end
    assign product = operand * coefficient;
    assign wide_product = {{16{product[31]}},product};
    function automatic logic signed [47:0] round14(input logic signed [47:0] value);
        logic signed [47:0] base;
        begin
            base = value >>> 14;
            if (value[13:0] > 14'h2000 || (value[13:0] == 14'h2000 && base[0]))
                base = base + 48'sd1;
            round14 = base;
        end
    endfunction
    assign rounded_a = round14(combined_a);
    assign rounded_b = round14(combined_b);

    always_ff @(posedge clk) begin
        if (!reset && load_valid && load_ready) input_memory[load_index] <= load_value;
        if (!reset && coefficient_valid && coefficient_ready) begin
            cosine_memory[{coefficient_position,coefficient_pair}] <= load_cosine;
            sine_memory[{coefficient_position,coefficient_pair}] <= load_sine;
        end
    end
    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE; position <= 0; pair_index <= 0;
            a <= 0; b <= 0; cosine <= 0; sine <= 0;
            combined_a <= 0; combined_b <= 0;
            result_a <= 0; result_b <= 0; saturated <= 0;
            step_valid <= 0; step_kind <= 0; step_pair <= 0;
            step_input <= 0; step_coefficient <= 0; step_product <= 0; step_total <= 0;
        end else begin
            step_valid <= 0;
            case (state)
                IDLE: if (start && start_ready) begin
                    position <= token_position[7:0]; pair_index <= 0;
                    combined_a <= 0; combined_b <= 0; saturated <= 0;
                    state <= READ;
                end
                READ: begin
                    a <= input_memory[result_index_a]; b <= input_memory[result_index_b];
                    cosine <= cosine_memory[coefficient_address]; sine <= sine_memory[coefficient_address];
                    state <= MUL_AC;
                end
                MUL_AC, MUL_BS, MUL_BC, MUL_AS: begin
                    step_valid <= 1; step_pair <= pair_index;
                    step_input <= operand; step_coefficient <= coefficient; step_product <= product;
                    case (state)
                        MUL_AC: begin
                            step_kind <= 0; step_total <= wide_product;
                            combined_a <= wide_product; state <= MUL_BS;
                        end
                        MUL_BS: begin
                            step_kind <= 1; step_total <= combined_a - wide_product;
                            combined_a <= combined_a - wide_product; state <= MUL_BC;
                        end
                        MUL_BC: begin
                            step_kind <= 2; step_total <= wide_product;
                            combined_b <= wide_product; state <= MUL_AS;
                        end
                        MUL_AS: begin
                            step_kind <= 3; step_total <= combined_b + wide_product;
                            combined_b <= combined_b + wide_product; state <= ROUND;
                        end
                        default: begin end
                    endcase
                end
                ROUND: begin
                    result_a <= rounded_a > 48'sd32767 ? 16'sh7fff : rounded_a < -48'sd32768 ? 16'sh8000 : rounded_a[15:0];
                    result_b <= rounded_b > 48'sd32767 ? 16'sh7fff : rounded_b < -48'sd32768 ? 16'sh8000 : rounded_b[15:0];
                    saturated <= {rounded_b > 48'sd32767 || rounded_b < -48'sd32768,
                                  rounded_a > 48'sd32767 || rounded_a < -48'sd32768};
                    state <= OUTPUT;
                end
                OUTPUT: if (result_ready) begin
                    if (pair_index == 5'd31) state <= IDLE;
                    else begin
                        pair_index <= pair_index + 5'd1;
                        combined_a <= 0; combined_b <= 0; saturated <= 0;
                        state <= READ;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
