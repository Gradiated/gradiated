    // The prefix must have quotient zero. Seed the long divider with it
    // and feed only the remaining low bits through its existing recurrence.
    task automatic exp_divide_start(input logic signed [63:0] a,
        input logic round_even,input state_t resume_state);
        localparam logic [63:0] DIVISOR = 64'd45426;
        logic [63:0] n, prefix, aligned;
        logic [6:0] steps;
        begin
            n = magnitude(a);
            case (resume_state)
                EXP_POWER: begin
                    prefix = n >> 6;
                    aligned = {n[5:0], 58'd0};
                    steps = 3;
                end
                EXP_INDEX: begin
                    prefix = n >> 8;
                    aligned = {n[7:0], 56'd0};
                    steps = 4;
                end
                EXP_DONE: begin
                    prefix = n >> 32;
                    aligned = {n[31:0], 32'd0};
                    steps = 16;
                end
                default: begin
                    prefix = DIVISOR;
                    aligned = 0;
                    steps = 0;
                end
            endcase

            divide_start(a, DIVISOR, round_even, resume_state);
            if (prefix < DIVISOR) begin
                numerator <= aligned;
                remainder <= {1'b0, prefix};
                remaining <= steps;
            end
        end
    endtask

