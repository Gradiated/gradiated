`timescale 1ns/1ps

module kda_state_bank #(
    parameter integer WIDTH = 24,
    parameter integer DEPTH = 1024,
    parameter integer ADDR_W = 10
) (
    input  wire                    clk,
    input  wire [ADDR_W-1:0]       read_addr,
    output reg signed [WIDTH-1:0]  read_data,
    input  wire                    write_en,
    input  wire [ADDR_W-1:0]       write_addr,
    input  wire signed [WIDTH-1:0] write_data
);
    (* ram_style = "block" *) reg signed [WIDTH-1:0] memory [0:DEPTH-1];

    always @(posedge clk) begin
        read_data <= memory[read_addr];
        if (write_en)
            memory[write_addr] <= write_data;
    end
endmodule
