// Two serial 16-coordinate attention heads, including integer softmax and V sum.
// Qrot/Krot units 2^-11, V/context units 2^-12, scores Q16, probabilities UQ15.
// Cache storage is external. Every read has one tagged response, held until ready.
`timescale 1ns/1ps
module attention (
    input logic clk, reset,
    input logic load_valid,
    output logic load_ready,
    input logic [4:0] load_index,
    input logic signed [15:0] load_value,
    input logic table_valid,
    output logic table_ready,
    input logic [8:0] table_index,
    input logic [31:0] table_value,
    input logic start,
    input logic [8:0] context_length,
    output logic start_ready, busy,
    output logic cache_read_valid,
    input logic cache_read_ready,
    output logic [8:0] cache_read_position,
    output logic [5:0] cache_read_coordinate,
    input logic cache_output_valid,
    output logic cache_output_ready,
    input logic [7:0] cache_output_position,
    input logic [4:0] cache_output_coordinate,
    input logic signed [15:0] cache_output_k, cache_output_v,
    output logic result_valid,
    input logic result_ready,
    output logic [4:0] result_index,
    output logic signed [15:0] result,
    output logic saturated, error,
    output logic observe_cache_wait,
    output logic score_valid, score_head,
    output logic [7:0] score_position,
    output logic signed [31:0] score_value,
    output logic exp_valid, exp_head,
    output logic [7:0] exp_position,
    output logic [31:0] exp_value,
    output logic probability_valid, probability_head,
    output logic [7:0] probability_position,
    output logic [15:0] probability_value,
    output logic step_valid, step_mode, step_head,
    output logic [7:0] step_position,
    output logic [3:0] step_coordinate,
    output logic signed [16:0] step_input,
    output logic signed [15:0] step_weight,
    output logic signed [32:0] step_product,
    output logic signed [47:0] step_sum
);
    typedef enum logic [4:0] {
        IDLE, SCORE_REQ, SCORE_DATA, SCORE_MAC, SCORE_SEND, SCORE_WAIT,
        EXP_READ, EXP_SEND, EXP_WAIT, PROB_READ, PROB_SEND, PROB_WAIT,
        CONTEXT_REQ, CONTEXT_DATA, CONTEXT_MAC, CONTEXT_SEND, CONTEXT_WAIT, OUTPUT
    } state_t;
    state_t state;
    logic signed [15:0] query_memory [0:31];
    logic [31:0] loaded;
    logic signed [31:0] scores [0:255];
    logic [31:0] exponentials [0:255];
    logic [15:0] probabilities [0:255];
    logic [8:0] length;
    logic head;
    logic [7:0] position;
    logic [3:0] coordinate;
    logic signed [31:0] maximum, narrowed_score;
    logic [63:0] exp_sum;
    logic signed [16:0] operand;
    logic signed [15:0] weight;
    (* keep = "true" *) logic signed [32:0] product;
    logic signed [47:0] accumulator;
    (* use_dsp = "no" *) logic signed [47:0] next_sum;
    logic scalar_cmd_valid, scalar_cmd_ready, scalar_result_valid, scalar_result_ready;
    logic scalar_table_ready, scalar_error;
    logic [2:0] scalar_op;
    logic signed [63:0] scalar_a, scalar_b, scalar_result;
    logic signed [7:0] scalar_shift, scalar_exponent;

    assign observe_cache_wait=(state==SCORE_DATA || state==CONTEXT_DATA) && !cache_output_valid;
    assign busy=state!=IDLE;
    assign load_ready=!reset && state==IDLE && !start && !table_valid;
    assign table_ready=!reset && state==IDLE && !start && !load_valid && scalar_table_ready;
    assign start_ready=!reset && state==IDLE && !load_valid && !table_valid && (&loaded) &&
                       context_length>0 && context_length<=9'd256;
    assign result_valid=!reset && state==OUTPUT;
    assign cache_read_valid=!reset && (state==SCORE_REQ || state==CONTEXT_REQ);
    assign cache_read_position={1'b0,position};
    assign cache_read_coordinate={1'b0,head,coordinate};
    assign cache_output_ready=!reset && (state==SCORE_DATA || state==CONTEXT_DATA);
    assign product=operand*weight;
    assign next_sum=accumulator+{{15{product[32]}},product};
    assign scalar_cmd_valid=state==SCORE_SEND || state==EXP_SEND || state==PROB_SEND || state==CONTEXT_SEND;
    assign scalar_result_ready=state==SCORE_WAIT || state==EXP_WAIT || state==PROB_WAIT || state==CONTEXT_WAIT;
    always_comb begin
        if(scalar_result>64'sd2147483647)narrowed_score=32'sh7fff_ffff;
        else if(scalar_result < -64'sd2147483648)narrowed_score=32'sh8000_0000;
        else narrowed_score=scalar_result[31:0];
    end
    fixed_scalar scalar (
        .clk(clk),.reset(reset),.cmd_valid(scalar_cmd_valid),.cmd_ready(scalar_cmd_ready),
        .cmd_op(scalar_op),.cmd_a(scalar_a),.cmd_b(scalar_b),.cmd_shift(scalar_shift),
        .table_valid(table_valid && table_ready),.table_ready(scalar_table_ready),.table_kind(1'b0),
        .table_index(table_index),.table_value(table_value),.result_valid(scalar_result_valid),
        .result_ready(scalar_result_ready),.result(scalar_result),.result_exponent(scalar_exponent),.error(scalar_error)
    );
    task automatic fail;
        begin result<=0;result_index<={head,coordinate};error<=1;state<=OUTPUT;end
    endtask
    task automatic scalar_shift_start(input logic signed [47:0] value,input logic signed [7:0] amount,input state_t next_state);
        begin
            scalar_a<={{16{value[47]}},value};scalar_b<=0;scalar_shift<=amount;scalar_op<=0;state<=next_state;
        end
    endtask

    always_ff @(posedge clk) begin
        if(!reset && load_valid && load_ready)query_memory[load_index]<=load_value;
        if(reset)begin
            state<=IDLE;loaded<=0;length<=0;head<=0;position<=0;coordinate<=0;
            maximum<=32'sh8000_0000;exp_sum<=0;operand<=0;weight<=0;accumulator<=0;
            scalar_op<=0;scalar_a<=0;scalar_b<=0;scalar_shift<=0;
            result<=0;result_index<=0;saturated<=0;error<=0;
            score_valid<=0;score_head<=0;score_position<=0;score_value<=0;
            exp_valid<=0;exp_head<=0;exp_position<=0;exp_value<=0;
            probability_valid<=0;probability_head<=0;probability_position<=0;probability_value<=0;
            step_valid<=0;step_mode<=0;step_head<=0;step_position<=0;step_coordinate<=0;
            step_input<=0;step_weight<=0;step_product<=0;step_sum<=0;
        end else begin
            score_valid<=0;exp_valid<=0;probability_valid<=0;step_valid<=0;
            if(load_valid && load_ready)loaded[load_index]<=1;
            case(state)
                IDLE: if(start && start_ready)begin
                    length<=context_length;head<=0;position<=0;coordinate<=0;accumulator<=0;
                    maximum<=32'sh8000_0000;exp_sum<=0;saturated<=0;error<=0;state<=SCORE_REQ;
                end
                SCORE_REQ: if(cache_read_ready)state<=SCORE_DATA;
                SCORE_DATA: if(cache_output_valid)begin
                    if(cache_output_position!=position || cache_output_coordinate!={head,coordinate})fail();
                    else begin
                        operand<={query_memory[{head,coordinate}][15],query_memory[{head,coordinate}]};
                        weight<=cache_output_k;state<=SCORE_MAC;
                    end
                end
                SCORE_MAC: begin
                    accumulator<=next_sum;step_valid<=1;step_mode<=0;step_head<=head;
                    step_position<=position;step_coordinate<=coordinate;step_input<=operand;
                    step_weight<=weight;step_product<=product;step_sum<=next_sum;
                    if(coordinate==15)scalar_shift_start(next_sum,-8'sd8,SCORE_SEND);
                    else begin coordinate<=coordinate+1'b1;state<=SCORE_REQ;end
                end
                SCORE_SEND: if(scalar_cmd_ready)state<=SCORE_WAIT;
                SCORE_WAIT: if(scalar_result_valid)begin
                    if(scalar_error)fail();
                    else begin
                        scores[position]<=narrowed_score;
                        score_valid<=1;score_head<=head;score_position<=position;score_value<=narrowed_score;
                        if(scalar_result>64'sd2147483647 || scalar_result < -64'sd2147483648)saturated<=1;
                        if(narrowed_score>maximum)maximum<=narrowed_score;
                        if({1'b0,position}+9'd1==length)begin position<=0;state<=EXP_READ;end
                        else begin position<=position+1'b1;coordinate<=0;accumulator<=0;state<=SCORE_REQ;end
                    end
                end
                EXP_READ: begin
                    scalar_a<=$signed({{32{scores[position][31]}},scores[position]})-
                              $signed({{32{maximum[31]}},maximum});
                    scalar_b<=0;scalar_op<=3;scalar_shift<=0;state<=EXP_SEND;
                end
                EXP_SEND: if(scalar_cmd_ready)state<=EXP_WAIT;
                EXP_WAIT: if(scalar_result_valid)begin
                    if(scalar_error || scalar_result<0 || scalar_result>64'sd2147483648)fail();
                    else begin
                        exponentials[position]<=scalar_result[31:0];exp_sum<=exp_sum+$unsigned(scalar_result);
                        exp_valid<=1;exp_head<=head;exp_position<=position;exp_value<=scalar_result[31:0];
                        if({1'b0,position}+9'd1==length)begin position<=0;state<=PROB_READ;end
                        else begin position<=position+1'b1;state<=EXP_READ;end
                    end
                end
                PROB_READ: begin
                    if(exp_sum==0 || exp_sum>64'h3fff_ffff_ffff_ffff)fail();
                    else begin
                        scalar_a<=$signed({17'd0,exponentials[position],15'd0});scalar_b<=$signed(exp_sum);
                        scalar_op<=1;scalar_shift<=0;state<=PROB_SEND;
                    end
                end
                PROB_SEND: if(scalar_cmd_ready)state<=PROB_WAIT;
                PROB_WAIT: if(scalar_result_valid)begin
                    if(scalar_error || scalar_result<0 || scalar_result>64'sd32768)fail();
                    else begin
                        probabilities[position]<=scalar_result[15:0];probability_valid<=1;
                        probability_head<=head;probability_position<=position;probability_value<=scalar_result[15:0];
                        if({1'b0,position}+9'd1==length)begin
                            position<=0;coordinate<=0;accumulator<=0;state<=CONTEXT_REQ;
                        end else begin position<=position+1'b1;state<=PROB_READ;end
                    end
                end
                CONTEXT_REQ: if(cache_read_ready)state<=CONTEXT_DATA;
                CONTEXT_DATA: if(cache_output_valid)begin
                    if(cache_output_position!=position || cache_output_coordinate!={head,coordinate})fail();
                    else begin
                        operand<=$signed({1'b0,probabilities[position]});weight<=cache_output_v;state<=CONTEXT_MAC;
                    end
                end
                CONTEXT_MAC: begin
                    accumulator<=next_sum;step_valid<=1;step_mode<=1;step_head<=head;
                    step_position<=position;step_coordinate<=coordinate;step_input<=operand;
                    step_weight<=weight;step_product<=product;step_sum<=next_sum;
                    if({1'b0,position}+9'd1==length)scalar_shift_start(next_sum,-8'sd15,CONTEXT_SEND);
                    else begin position<=position+1'b1;state<=CONTEXT_REQ;end
                end
                CONTEXT_SEND: if(scalar_cmd_ready)state<=CONTEXT_WAIT;
                CONTEXT_WAIT: if(scalar_result_valid)begin
                    if(scalar_error)fail();
                    else begin
                        result_index<={head,coordinate};
                        if(scalar_result>64'sd32767)begin result<=16'sh7fff;saturated<=1;end
                        else if(scalar_result < -64'sd32768)begin result<=16'sh8000;saturated<=1;end
                        else result<=scalar_result[15:0];
                        state<=OUTPUT;
                    end
                end
                OUTPUT: if(result_ready)begin
                    if(error)state<=IDLE;
                    else if(coordinate==15)begin
                        if(head)state<=IDLE;
                        else begin
                            head<=1;position<=0;coordinate<=0;accumulator<=0;
                            maximum<=32'sh8000_0000;exp_sum<=0;state<=SCORE_REQ;
                        end
                    end else begin position<=0;coordinate<=coordinate+1'b1;accumulator<=0;state<=CONTEXT_REQ;end
                end
                default: state<=IDLE;
            endcase
        end
    end
endmodule
