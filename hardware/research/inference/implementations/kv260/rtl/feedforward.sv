// Selected SwiGLU feed-forward sublayer. Caller supplies norm2 at exponent -11.
// Gate/up/down matrices are loaded data, not compiled answers. Three dense
// instances are used here; sharing a physical lane between them is later work.
`timescale 1ns/1ps
module feedforward (
    input logic clk, reset,
    input logic input_valid,
    output logic input_ready,
    input logic [7:0] input_address,
    input logic signed [15:0] input_value,
    input logic weight_valid,
    output logic weight_ready,
    input logic [1:0] weight_bank,
    input logic [8:0] weight_row,
    input logic [7:0] weight_address,
    input logic signed [15:0] weight_value,
    input logic table_valid,
    output logic table_ready,
    input logic [8:0] table_index,
    input logic [31:0] table_value,
    input logic start,
    output logic start_ready, busy,
    output logic result_valid,
    input logic result_ready,
    output logic [8:0] result_row,
    output logic signed [15:0] result,
    output logic saturated, error,
    output logic element_valid,
    output logic [6:0] element_index,
    output logic signed [15:0] element_gate, element_up, element_silu, element_hidden,
    output logic [3:0] element_saturated
);
    typedef enum logic [4:0] {IDLE, PAIR, EXP_SEND, EXP_WAIT, SIG_SEND, SIG_WAIT,
        GATE_MUL_SEND, GATE_MUL_WAIT, SILU_SHIFT_SEND, SILU_SHIFT_WAIT,
        HIDDEN_MUL_SEND, HIDDEN_MUL_WAIT, HIDDEN_SHIFT_SEND, HIDDEN_SHIFT_WAIT,
        STORE, DOWN_START, DOWN_RUN, FAIL} state_t;
    state_t state;
    logic g_input_ready,u_input_ready,g_weight_ready,u_weight_ready,d_weight_ready;
    logic g_start_ready,u_start_ready,d_start_ready,g_busy,u_busy,d_busy;
    logic g_valid,u_valid,d_valid,g_ready,u_ready,d_ready;
    logic signed [15:0] g_result,u_result,d_result;
    logic [8:0] g_row,u_row,d_row;
    logic g_saturated,u_saturated,d_saturated,d_input_ready;
    logic load_input,load_weight,launch,load_table;
    logic [6:0] index;
    logic signed [15:0] gate_value,up_value,silu_value,hidden_value;
    logic [3:0] clipping;
    logic signed [63:0] gate_wide,up_wide,silu_wide,decay,sigmoid,scratch;
    logic sc_valid,sc_ready,sc_result_valid,sc_result_ready,sc_error,sc_table_ready;
    logic [2:0] sc_op;
    logic signed [63:0] sc_a,sc_b,sc_result;
    logic signed [7:0] sc_shift,sc_exponent;

    assign busy=state!=IDLE;
    assign input_ready=!reset && state==IDLE && !start && g_input_ready && u_input_ready;
    assign weight_ready=!reset && state==IDLE && !start &&
        (weight_bank==0 ? g_weight_ready : weight_bank==1 ? u_weight_ready : weight_bank==2 ? d_weight_ready : 1'b0);
    assign table_ready=!reset && state==IDLE && !start && sc_table_ready;
    assign start_ready=!reset && state==IDLE && !input_valid && !weight_valid && !table_valid &&
                       g_start_ready && u_start_ready && d_start_ready && sc_ready;
    // Forward offers, not acceptance pulses. Child-ready already controls the
    // actual RAM write. Making child-valid depend on child-ready fed a loop
    // through dense.start_ready -> launch -> dense.input/weight_ready.
    // Gate/up have identical input-address checks and are idle together here.
    assign load_input=input_valid && !reset && state==IDLE && !start;
    assign load_weight=weight_valid && !reset && state==IDLE && !start;
    assign load_table=table_valid && !reset && state==IDLE && !start;
    assign launch=start && start_ready;
    assign g_ready=state==PAIR && u_valid;
    assign u_ready=state==PAIR && g_valid;
    assign d_ready=state==DOWN_RUN && result_ready;
    assign result_valid=(state==DOWN_RUN && d_valid) || state==FAIL;
    assign result=state==FAIL ? 16'sd0 : d_result;
    assign result_row=state==FAIL ? 9'd0 : d_row;
    assign saturated=state==DOWN_RUN && d_saturated;
    assign gate_wide={{48{gate_value[15]}},gate_value};
    assign up_wide={{48{up_value[15]}},up_value};
    assign silu_wide={{48{silu_value[15]}},silu_value};

    dense #(.INPUTS(32),.OUTPUTS(128),.SHIFT(16),.RESULT_BITS(16)) gate_dense (
        .clk(clk),.reset(reset),.input_valid(load_input),.input_ready(g_input_ready),
        .input_address(input_address),.input_value(input_value),
        .weight_valid(load_weight && weight_bank==0),.weight_ready(g_weight_ready),
        .weight_row(weight_row),.weight_address(weight_address),.weight_value(weight_value),
        .start(launch),.start_ready(g_start_ready),.busy(g_busy),
        .result_valid(g_valid),.result_ready(g_ready),.result(g_result),.result_row(g_row),.saturated(g_saturated),
        .step_valid(),.step_index(),.step_row(),.step_input(),.step_weight(),.step_product(),.step_sum());
    dense #(.INPUTS(32),.OUTPUTS(128),.SHIFT(15),.RESULT_BITS(16)) up_dense (
        .clk(clk),.reset(reset),.input_valid(load_input),.input_ready(u_input_ready),
        .input_address(input_address),.input_value(input_value),
        .weight_valid(load_weight && weight_bank==1),.weight_ready(u_weight_ready),
        .weight_row(weight_row),.weight_address(weight_address),.weight_value(weight_value),
        .start(launch),.start_ready(u_start_ready),.busy(u_busy),
        .result_valid(u_valid),.result_ready(u_ready),.result(u_result),.result_row(u_row),.saturated(u_saturated),
        .step_valid(),.step_index(),.step_row(),.step_input(),.step_weight(),.step_product(),.step_sum());
    dense #(.INPUTS(128),.OUTPUTS(32),.SHIFT(15),.RESULT_BITS(16)) down_dense (
        .clk(clk),.reset(reset),.input_valid(state==STORE),.input_ready(d_input_ready),
        .input_address({1'b0,index}),.input_value(hidden_value),
        .weight_valid(load_weight && weight_bank==2),.weight_ready(d_weight_ready),
        .weight_row(weight_row),.weight_address(weight_address),.weight_value(weight_value),
        .start(state==DOWN_START),.start_ready(d_start_ready),.busy(d_busy),
        .result_valid(d_valid),.result_ready(d_ready),.result(d_result),.result_row(d_row),.saturated(d_saturated),
        .step_valid(),.step_index(),.step_row(),.step_input(),.step_weight(),.step_product(),.step_sum());

    fixed_scalar scalar (
        .clk(clk),.reset(reset),.cmd_valid(sc_valid),.cmd_ready(sc_ready),
        .cmd_op(sc_op),.cmd_a(sc_a),.cmd_b(sc_b),.cmd_shift(sc_shift),
        .result_valid(sc_result_valid),.result_ready(sc_result_ready),.result(sc_result),
        .result_exponent(sc_exponent),.error(sc_error),
        .table_valid(load_table),.table_ready(sc_table_ready),.table_kind(1'b0),
        .table_index(table_index),.table_value(table_value));

    always_comb begin
        sc_valid=0;sc_op=0;sc_a=0;sc_b=0;sc_shift=0;sc_result_ready=0;
        case(state)
            EXP_SEND: begin sc_valid=1;sc_op=3;sc_a=gate_wide>=0 ? -(gate_wide<<<6) : gate_wide<<<6;end
            SIG_SEND: begin
                sc_valid=1;sc_op=1;sc_a=gate_value>=0 ? 64'sd4611686018427387904 : decay<<<31;
                sc_b=64'sd2147483648+decay;
            end
            GATE_MUL_SEND: begin sc_valid=1;sc_op=2;sc_a=gate_wide;sc_b=sigmoid;end
            SILU_SHIFT_SEND: begin sc_valid=1;sc_a=scratch;sc_shift=-8'sd30;end
            HIDDEN_MUL_SEND: begin sc_valid=1;sc_op=2;sc_a=silu_wide;sc_b=up_wide;end
            HIDDEN_SHIFT_SEND: begin sc_valid=1;sc_a=scratch;sc_shift=-8'sd13;end
            EXP_WAIT,SIG_WAIT,GATE_MUL_WAIT,SILU_SHIFT_WAIT,HIDDEN_MUL_WAIT,HIDDEN_SHIFT_WAIT:sc_result_ready=1;
            default:begin end
        endcase
    end

    function automatic logic signed [15:0] clip16(input logic signed [63:0] value);
        clip16=value>64'sd32767 ? 16'sh7fff : value< -64'sd32768 ? 16'sh8000 : value[15:0];
    endfunction

    always_ff @(posedge clk) begin
        if(reset)begin
            state<=IDLE;index<=0;gate_value<=0;up_value<=0;silu_value<=0;hidden_value<=0;
            clipping<=0;decay<=0;sigmoid<=0;scratch<=0;error<=0;
            element_valid<=0;element_index<=0;element_gate<=0;element_up<=0;element_silu<=0;element_hidden<=0;element_saturated<=0;
        end else begin
            element_valid<=0;
            if(sc_result_valid && sc_result_ready && sc_error)begin
                error<=1;state<=FAIL;
            end else case(state)
                IDLE:if(launch)begin state<=PAIR;index<=0;error<=0;end
                PAIR:if(g_valid && u_valid)begin
                    if(g_row!=u_row || int'(g_row)!=int'(index))begin error<=1;state<=FAIL;end
                    else begin
                        gate_value<=g_result;up_value<=u_result;clipping<={2'b00,u_saturated,g_saturated};state<=EXP_SEND;
                    end
                end
                EXP_SEND:if(sc_ready)state<=EXP_WAIT;
                EXP_WAIT:if(sc_result_valid)begin decay<=sc_result;state<=SIG_SEND;end
                SIG_SEND:if(sc_ready)state<=SIG_WAIT;
                SIG_WAIT:if(sc_result_valid)begin sigmoid<=sc_result;state<=GATE_MUL_SEND;end
                GATE_MUL_SEND:if(sc_ready)state<=GATE_MUL_WAIT;
                GATE_MUL_WAIT:if(sc_result_valid)begin scratch<=sc_result;state<=SILU_SHIFT_SEND;end
                SILU_SHIFT_SEND:if(sc_ready)state<=SILU_SHIFT_WAIT;
                SILU_SHIFT_WAIT:if(sc_result_valid)begin
                    silu_value<=clip16(sc_result);clipping[2]<=sc_result>64'sd32767 || sc_result< -64'sd32768;state<=HIDDEN_MUL_SEND;
                end
                HIDDEN_MUL_SEND:if(sc_ready)state<=HIDDEN_MUL_WAIT;
                HIDDEN_MUL_WAIT:if(sc_result_valid)begin scratch<=sc_result;state<=HIDDEN_SHIFT_SEND;end
                HIDDEN_SHIFT_SEND:if(sc_ready)state<=HIDDEN_SHIFT_WAIT;
                HIDDEN_SHIFT_WAIT:if(sc_result_valid)begin
                    hidden_value<=clip16(sc_result);clipping[3]<=sc_result>64'sd32767 || sc_result< -64'sd32768;state<=STORE;
                end
                STORE:if(d_input_ready)begin
                    element_valid<=1;element_index<=index;element_gate<=gate_value;element_up<=up_value;
                    element_silu<=silu_value;element_hidden<=hidden_value;element_saturated<=clipping;
                    if(index==127)state<=DOWN_START;
                    else begin index<=index+1'b1;state<=PAIR;end
                end
                DOWN_START:if(d_start_ready)state<=DOWN_RUN;
                DOWN_RUN:if(d_valid && result_ready && d_row==31)state<=IDLE;
                // Scalar/configuration faults hold an error response until reset;
                // unfinished dense work also needs that synchronous cancellation.
                FAIL:begin end
                default:begin error<=1;state<=FAIL;end
            endcase
        end
    end
endmodule
