// Separate append-only KV cache: K after RoPE, V unchanged, 256 x 32 signed16 each.
// A row becomes readable only when all 32 coordinate pairs are committed.
`timescale 1ns/1ps
module kv_cache (
    input logic clk, reset,
    input logic write_valid,
    output logic write_ready,
    input logic [8:0] write_position,
    input logic [5:0] write_coordinate,
    input logic signed [15:0] write_k, write_v,
    input logic read_valid,
    output logic read_ready,
    input logic [8:0] read_position,
    input logic [5:0] read_coordinate,
    output logic output_valid,
    input logic output_ready,
    output logic [7:0] output_position,
    output logic [4:0] output_coordinate,
    output logic signed [15:0] output_k, output_v,
    output logic [8:0] token_count,
    output logic [4:0] next_coordinate,
    output logic commit_valid
);
    logic signed [15:0] k_memory [0:8191], v_memory [0:8191];
    logic pending;
    assign write_ready = !reset && !pending && !read_valid && token_count < 9'd256 &&
                         write_position == token_count && write_coordinate == {1'b0,next_coordinate};
    assign read_ready = !reset && !pending && !write_valid && read_position < token_count && read_coordinate < 6'd32;
    assign output_valid = pending && !reset;
    // No RAM reset loop: validity metadata hides retained words after reset.
    always_ff @(posedge clk) begin
        if (!reset && write_valid && write_ready) begin
            k_memory[{write_position[7:0],write_coordinate[4:0]}] <= write_k;
            v_memory[{write_position[7:0],write_coordinate[4:0]}] <= write_v;
        end
    end
    always_ff @(posedge clk) begin
        if (reset) begin
            pending <= 0; token_count <= 0; next_coordinate <= 0; commit_valid <= 0;
            output_position <= 0; output_coordinate <= 0; output_k <= 0; output_v <= 0;
        end else begin
            commit_valid <= 0;
            if (write_valid && write_ready) begin
                if (next_coordinate == 5'd31) begin
                    token_count <= token_count + 9'd1;
                    next_coordinate <= 0; commit_valid <= 1;
                end else next_coordinate <= next_coordinate + 5'd1;
            end
            if (read_valid && read_ready) begin
                output_k <= k_memory[{read_position[7:0],read_coordinate[4:0]}];
                output_v <= v_memory[{read_position[7:0],read_coordinate[4:0]}];
                output_position <= read_position[7:0]; output_coordinate <= read_coordinate[4:0];
                pending <= 1;
            end else if (output_valid && output_ready) pending <= 0;
        end
    end
endmodule
