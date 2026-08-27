`timescale 1ns/1ps

module tb_kda_core;
`ifdef KDA_TARGET_L16
    localparam integer D = 128;
    localparam integer LANES = 16;
`elsif KDA_TARGET_L32
    localparam integer D = 128;
    localparam integer LANES = 32;
`else
    localparam integer D = 16;
    localparam integer LANES = 4;
`endif
    localparam integer TOKENS = 3;
    localparam integer EXPECTED_CYCLES = 7 * D * (D / LANES);

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg start = 1'b0;
    reg clear_state = 1'b0;
    reg cfg_wr_en = 1'b0;
    reg [2:0] cfg_wr_kind = 3'd0;
    reg [15:0] cfg_wr_addr = 16'd0;
    reg [31:0] cfg_wr_data = 32'd0;
    reg [15:0] out_rd_addr = 16'd0;
    wire [31:0] out_rd_data;
    wire busy;
    wire done;
    wire [31:0] cycles;

    reg [7:0] q_values [0:TOKENS*D-1];
    reg [7:0] k_values [0:TOKENS*D-1];
    reg [7:0] v_values [0:TOKENS*D-1];
    reg [7:0] alpha_values [0:TOKENS*D-1];
    reg [7:0] beta_values [0:TOKENS-1];
    reg [31:0] expected_values [0:TOKENS*D-1];

    integer token_index;
    integer vector_index;
    integer errors = 0;

    always #5 clk = ~clk;

    kda_core #(.HEAD_DIM(D), .LANES(LANES)) dut (
        .clk(clk),
        .rst_n(rst_n),
        .start(start),
        .clear_state(clear_state),
        .cfg_wr_en(cfg_wr_en),
        .cfg_wr_kind(cfg_wr_kind),
        .cfg_wr_addr(cfg_wr_addr),
        .cfg_wr_data(cfg_wr_data),
        .out_rd_addr(out_rd_addr),
        .out_rd_data(out_rd_data),
        .busy(busy),
        .done(done),
        .cycles(cycles)
    );

    task write_config;
        input [2:0] kind;
        input [15:0] address;
        input [31:0] data;
        begin
            @(negedge clk);
            cfg_wr_kind = kind;
            cfg_wr_addr = address;
            cfg_wr_data = data;
            cfg_wr_en = 1'b1;
            @(negedge clk);
            cfg_wr_en = 1'b0;
        end
    endtask

    task pulse_clear;
        begin
            @(negedge clk);
            clear_state = 1'b1;
            @(negedge clk);
            clear_state = 1'b0;
            wait (busy == 1'b1);
            wait (busy == 1'b0 && done == 1'b1);
        end
    endtask

    task load_token;
        input integer selected_token;
        begin
            for (vector_index = 0; vector_index < D; vector_index = vector_index + 1) begin
                write_config(3'd0, vector_index, {24'd0, q_values[selected_token*D+vector_index]});
                write_config(3'd1, vector_index, {24'd0, k_values[selected_token*D+vector_index]});
                write_config(3'd2, vector_index, {24'd0, v_values[selected_token*D+vector_index]});
                write_config(3'd3, vector_index, {24'd0, alpha_values[selected_token*D+vector_index]});
            end
            write_config(3'd4, 16'd0, {24'd0, beta_values[selected_token]});
        end
    endtask

    task run_and_check;
        input integer selected_token;
        begin
            @(negedge clk);
            start = 1'b1;
            @(negedge clk);
            start = 1'b0;
            wait (busy == 1'b1);
            wait (busy == 1'b0 && done == 1'b1);
            if (cycles !== EXPECTED_CYCLES) begin
                $display("cycle mismatch token=%0d actual=%0d expected=%0d", selected_token, cycles, EXPECTED_CYCLES);
                errors = errors + 1;
            end
            for (vector_index = 0; vector_index < D; vector_index = vector_index + 1) begin
                out_rd_addr = vector_index;
                #1;
                if ($signed(out_rd_data) !== $signed(expected_values[selected_token*D+vector_index])) begin
                    $display("output mismatch token=%0d index=%0d actual=%0d expected=%0d", selected_token, vector_index, $signed(out_rd_data), $signed(expected_values[selected_token*D+vector_index]));
                    errors = errors + 1;
                end
            end
        end
    endtask

    initial begin
`ifdef KDA_TARGET
        $readmemh("sim/fixtures_target/q.memh", q_values);
        $readmemh("sim/fixtures_target/k.memh", k_values);
        $readmemh("sim/fixtures_target/v.memh", v_values);
        $readmemh("sim/fixtures_target/alpha.memh", alpha_values);
        $readmemh("sim/fixtures_target/beta.memh", beta_values);
        $readmemh("sim/fixtures_target/expected.memh", expected_values);
`else
        $readmemh("sim/fixtures/q.memh", q_values);
        $readmemh("sim/fixtures/k.memh", k_values);
        $readmemh("sim/fixtures/v.memh", v_values);
        $readmemh("sim/fixtures/alpha.memh", alpha_values);
        $readmemh("sim/fixtures/beta.memh", beta_values);
        $readmemh("sim/fixtures/expected.memh", expected_values);
`endif

        repeat (4) @(negedge clk);
        rst_n = 1'b1;
        pulse_clear();
        if (cycles !== D * (D / LANES)) begin
            $display("clear cycle mismatch actual=%0d expected=%0d", cycles, D * (D / LANES));
            errors = errors + 1;
        end

        for (token_index = 0; token_index < TOKENS; token_index = token_index + 1) begin
            load_token(token_index);
            run_and_check(token_index);
        end

        pulse_clear();
        load_token(0);
        run_and_check(0);

        if (errors == 0) begin
            $display("PASS kda_core tokens=%0d head_dim=%0d lanes=%0d", TOKENS, D, LANES);
            $finish;
        end
        $fatal(1, "FAIL kda_core errors=%0d", errors);
    end
endmodule
