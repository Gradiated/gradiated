// Serial 32-coordinate RMSNorm using the checked fixed_scalar arithmetic unit.
// SOURCE_EXP, GAIN_EXP and OUTPUT_EXP are static binary exponents, not floats.
// Reset cancels work and invalidates load metadata; input/gain/table RAM bits survive.
`timescale 1ns/1ps
module rmsnorm #(
    parameter integer SOURCE_EXP=-14,
    parameter integer GAIN_EXP=-14,
    parameter integer OUTPUT_EXP=-11
) (
    input logic clk,reset,
    input logic load_valid,
    output logic load_ready,
    input logic [4:0] load_address,
    input logic signed [15:0] load_input,load_gain,
    input logic start,
    output logic start_ready,busy,
    input logic table_valid,
    output logic table_ready,
    input logic table_kind,
    input logic [8:0] table_index,
    input logic [31:0] table_value,
    output logic result_valid,
    input logic result_ready,
    output logic [4:0] result_index,
    output logic signed [15:0] result,
    output logic saturated,error
);
    typedef enum logic [3:0] {
        IDLE,SQUARE_SEND,SQUARE_WAIT,RSHIFT_SEND,RSHIFT_WAIT,
        RSQRT_SEND,RSQRT_WAIT,XY_SEND,XY_WAIT,GAIN_SEND,GAIN_WAIT,
        ROUND_SEND,ROUND_WAIT,OUTPUT
    } state_t;
    state_t state;
    logic signed [15:0] input_memory[0:31],gain_memory[0:31];
    logic [31:0] loaded;
    logic [4:0] coordinate;
    logic [47:0] squares;
    logic signed [63:0] r,y,xy,product;
    logic signed [7:0] exponent;
    logic scalar_cmd_valid,scalar_cmd_ready,scalar_result_valid,scalar_result_ready;
    logic scalar_table_valid,scalar_table_ready,scalar_error;
    logic [2:0] scalar_op;
    logic signed [63:0] scalar_a,scalar_b,scalar_result;
    logic signed [7:0] scalar_shift,scalar_exponent;
    logic signed [63:0] next_squares;
    integer output_shift;

    fixed_scalar scalar(
        .clk(clk),.reset(reset),.cmd_valid(scalar_cmd_valid),.cmd_ready(scalar_cmd_ready),
        .cmd_op(scalar_op),.cmd_a(scalar_a),.cmd_b(scalar_b),.cmd_shift(scalar_shift),
        .table_valid(scalar_table_valid),.table_ready(scalar_table_ready),
        .table_kind(table_kind),.table_index(table_index),.table_value(table_value),
        .result_valid(scalar_result_valid),.result_ready(scalar_result_ready),
        .result(scalar_result),.result_exponent(scalar_exponent),.error(scalar_error)
    );
    assign load_ready=state==IDLE && !reset && !start && !table_valid;
    assign start_ready=state==IDLE && !reset && !load_valid && !table_valid && (&loaded);
    assign busy=state!=IDLE;
    assign scalar_table_valid=state==IDLE && !start && !load_valid && table_valid;
    assign table_ready=state==IDLE && !start && !load_valid && scalar_table_ready;
    assign result_valid=state==OUTPUT && !reset;
    assign result_index=coordinate;
    assign next_squares=$signed({16'd0,squares})+scalar_result;

    always_comb begin
        scalar_cmd_valid=0;scalar_result_ready=0;scalar_op=0;scalar_a=0;scalar_b=0;scalar_shift=0;
        output_shift=SOURCE_EXP+GAIN_EXP-30-int'(exponent)-OUTPUT_EXP;
        case(state)
            SQUARE_SEND: begin
                scalar_cmd_valid=1;scalar_op=2;
                scalar_a={{48{input_memory[coordinate][15]}},input_memory[coordinate]};scalar_b=scalar_a;
            end
            RSHIFT_SEND: begin
                scalar_cmd_valid=1;scalar_op=0;scalar_a=$signed({16'd0,squares});
                scalar_shift=8'(2*SOURCE_EXP+27);
            end
            RSQRT_SEND: begin scalar_cmd_valid=1;scalar_op=4;scalar_a=r;end
            XY_SEND: begin
                scalar_cmd_valid=1;scalar_op=2;
                scalar_a={{48{input_memory[coordinate][15]}},input_memory[coordinate]};scalar_b=y;
            end
            GAIN_SEND: begin
                scalar_cmd_valid=1;scalar_op=2;scalar_a=xy;
                scalar_b={{48{gain_memory[coordinate][15]}},gain_memory[coordinate]};
            end
            ROUND_SEND: begin scalar_cmd_valid=1;scalar_op=0;scalar_a=product;scalar_shift=8'(output_shift);end
            SQUARE_WAIT,RSHIFT_WAIT,RSQRT_WAIT,XY_WAIT,GAIN_WAIT,ROUND_WAIT:scalar_result_ready=1;
            default:begin end
        endcase
    end
    task automatic reject;
        begin result<=0;saturated<=0;error<=1;state<=OUTPUT;end
    endtask
    always_ff @(posedge clk) begin
        if(!reset && load_valid && load_ready)begin
            input_memory[load_address]<=load_input;gain_memory[load_address]<=load_gain;
        end
        if(reset)begin
            state<=IDLE;loaded<=0;coordinate<=0;squares<=0;r<=0;y<=0;xy<=0;product<=0;exponent<=0;
            result<=0;saturated<=0;error<=0;
        end else begin
            if(load_valid && load_ready)loaded[load_address]<=1;
            case(state)
                IDLE:if(start && start_ready)begin
                    coordinate<=0;squares<=0;saturated<=0;error<=0;
                    if(2*SOURCE_EXP+27 < -128 || 2*SOURCE_EXP+27 > 127)reject();
                    else state<=SQUARE_SEND;
                end
                SQUARE_SEND:if(scalar_cmd_valid && scalar_cmd_ready)state<=SQUARE_WAIT;
                SQUARE_WAIT:if(scalar_result_valid)begin
                    if(scalar_error || scalar_result<0 || next_squares>=64'sh8000_0000_0000 || next_squares<0)reject();
                    else begin
                        squares<=next_squares[47:0];
                        if(coordinate==31)begin coordinate<=0;state<=RSHIFT_SEND;end
                        else begin coordinate<=coordinate+5'd1;state<=SQUARE_SEND;end
                    end
                end
                RSHIFT_SEND:if(scalar_cmd_valid && scalar_cmd_ready)state<=RSHIFT_WAIT;
                RSHIFT_WAIT:if(scalar_result_valid)begin
                    if(scalar_error || scalar_result<0 || scalar_result>64'sh7fff_ffff_ffff_ffff-64'sd42950)reject();
                    else begin r<=scalar_result+64'sd42950;state<=RSQRT_SEND;end
                end
                RSQRT_SEND:if(scalar_cmd_valid && scalar_cmd_ready)state<=RSQRT_WAIT;
                RSQRT_WAIT:if(scalar_result_valid)begin
                    if(scalar_error)reject();
                    else begin y<=scalar_result;exponent<=scalar_exponent;state<=XY_SEND;end
                end
                XY_SEND:if(scalar_cmd_valid && scalar_cmd_ready)state<=XY_WAIT;
                XY_WAIT:if(scalar_result_valid)begin
                    if(scalar_error)reject();else begin xy<=scalar_result;state<=GAIN_SEND;end
                end
                GAIN_SEND:if(scalar_cmd_valid && scalar_cmd_ready)state<=GAIN_WAIT;
                GAIN_WAIT:if(scalar_result_valid)begin
                    if(scalar_error || output_shift < -128 || output_shift > 127)reject();
                    else begin product<=scalar_result;state<=ROUND_SEND;end
                end
                ROUND_SEND:if(scalar_cmd_valid && scalar_cmd_ready)state<=ROUND_WAIT;
                ROUND_WAIT:if(scalar_result_valid)begin
                    if(scalar_error)reject();
                    else begin
                        if(scalar_result>32767)begin result<=32767;saturated<=1;end
                        else if(scalar_result< -32768)begin result<=-32768;saturated<=1;end
                        else begin result<=scalar_result[15:0];saturated<=0;end
                        state<=OUTPUT;
                    end
                end
                OUTPUT:if(result_ready)begin
                    if(error || coordinate==31)state<=IDLE;
                    else begin coordinate<=coordinate+5'd1;state<=XY_SEND;end
                end
                default:state<=IDLE;
            endcase
        end
    end
endmodule
