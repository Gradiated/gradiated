
// The normalisation scalars retain command, sign, rounding and error state.
// This unit owns only the unsigned magnitude datapath and its result owner.
module rmsnorm_shared_mul (
    input logic clk, reset,
    input logic [2:0] request,
    output logic [2:0] grant,
    input logic [2:0][63:0] operand_a, operand_b,
    output logic [2:0] result_valid,
    input logic [2:0] result_ready,
    output logic [127:0] result
);
    typedef enum logic [2:0] {IDLE, ROWS, PAIRS, REDUCE, RESULT} state_t;
    state_t state;
    logic [2:0] owner;
    logic [63:0] multiplicand, multiplier;
    logic [79:0] product_rows[0:3];
    logic [95:0] product_halves[0:1];
    logic [127:0] product_sum;

    // In the transformer only one norm can request at any clock. Fixed
    // priority also makes simultaneous requests safe: a denied requester
    // keeps its operands stable and waits for a grant.
    always_comb begin
        grant = 3'b000;
        multiplicand = 64'd0;
        multiplier = 64'd0;
        if (!reset && state == IDLE) begin
            if (request[0]) begin
                grant = 3'b001;
                multiplicand = operand_a[0];
                multiplier = operand_b[0];
            end else if (request[1]) begin
                grant = 3'b010;
                multiplicand = operand_a[1];
                multiplier = operand_b[1];
            end else if (request[2]) begin
                grant = 3'b100;
                multiplicand = operand_a[2];
                multiplier = operand_b[2];
            end
        end
    end

    assign result = product_sum;
    assign result_valid = (!reset && state == RESULT) ? owner : 3'b000;
    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            owner <= 3'b000;
        end else begin
            case (state)
                IDLE: if (|grant) begin
                    owner <= grant;
                    state <= ROWS;
                end
                ROWS: state <= PAIRS;
                PAIRS: state <= REDUCE;
                REDUCE: state <= RESULT;
                RESULT: if (|(result_valid & result_ready)) begin
                    state <= IDLE;
                    owner <= 3'b000;
                end
                default: begin
                    state <= IDLE;
                    owner <= 3'b000;
                end
            endcase
        end
    end

    // DSP_LIMB_DATAPATH
endmodule
