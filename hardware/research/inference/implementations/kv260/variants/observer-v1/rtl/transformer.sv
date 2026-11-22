// One-token fixed-point decoder datapath. Sampling and token feedback are host work.
// All neural layers, including norms/softmax/SwiGLU, execute in these RTL modules.
// Parameters/tables arrive through an ordered, idle-only load interface.
`timescale 1ns/1ps
module transformer (
    input logic clk,reset,
    input logic weight_valid,
    output logic weight_ready,
    input logic [3:0] weight_bank,
    input logic [15:0] weight_address,
    input logic [31:0] weight_value,
    output logic configured,
    input logic clear_context,
    input logic token_valid,
    output logic token_ready,
    input logic [8:0] token,
    output logic busy,
    output logic logit_valid,
    input logic logit_ready,
    output logic [8:0] logit_index,
    output logic signed [31:0] logit,
    output logic saturated,error,
    output logic [8:0] context_count,
    output logic [4:0] phase,
    output logic [5:0] observe
);
    typedef enum logic [4:0] {IDLE,EMBED_READ,EMBED_LOAD,N1_START,N1_WAIT,
        FRONT_START,FRONT_WAIT,ATT_START,ATT_WAIT,O_START,O_WAIT,N2_START,N2_WAIT,
        FF_START,FF_WAIT,NF_START,NF_WAIT,LOGIT_START,LOGIT_WAIT,FAULT} state_t;
    state_t state;
    logic [3:0] next_bank;
    logic [15:0] next_word,bank_words;
    logic [8:0] current_token;
    logic [4:0] coordinate;
    logic signed [15:0] embedding_memory[0:10239],gain1[0:31],gain2[0:31],gain3[0:31];
    logic signed [15:0] q_first_row[0:31],embedding[0:31],residual1[0:31],embed_value;
    logic accept_weight,weight_offer,load_target_ready,front_reset;
    logic n1_load_ready,n1_start_ready,n1_busy,n1_valid,n1_ready,n1_clip,n1_error,n1_table_ready;
    logic n2_load_ready,n2_start_ready,n2_busy,n2_valid,n2_ready,n2_clip,n2_error,n2_table_ready;
    logic nf_load_ready,nf_start_ready,nf_busy,nf_valid,nf_ready,nf_clip,nf_error,nf_table_ready;
    logic [4:0] n1_index,n2_index,nf_index;
    logic signed [15:0] n1_result,n2_result,nf_result;
    logic front_load_ready,front_coeff_ready,front_start_ready,front_busy,query_valid,query_ready,front_clip;
    logic [4:0] query_coordinate;
    logic signed [15:0] query_value;
    logic cache_read_valid,cache_read_ready,cache_output_valid,cache_output_ready;
    logic [8:0] cache_read_position;
    logic [5:0] cache_read_coordinate;
    logic [7:0] cache_output_position;
    logic [4:0] cache_output_coordinate;
    logic signed [15:0] cache_k,cache_v;
    logic att_load_ready,att_start_ready,att_busy,att_valid,att_ready,att_clip,att_error,att_table_ready;
    logic [4:0] att_index;
    logic signed [15:0] att_result;
    logic o_input_ready,o_weight_ready,o_start_ready,o_busy,o_valid,o_ready,o_clip;
    logic [8:0] o_row;
    logic signed [15:0] o_result;
    logic ff_input_ready,ff_weight_ready,ff_table_ready,ff_start_ready,ff_busy,ff_valid,ff_ready,ff_clip,ff_error;
    logic ff_element_valid;
    logic [6:0] ff_element_index;
    logic signed [15:0] ff_element_gate,ff_element_up,ff_element_silu,ff_element_hidden;
    logic [3:0] ff_element_clip;
    logic [8:0] ff_row;
    logic signed [15:0] ff_result;
    logic l_input_ready,l_weight_ready,l_start_ready,l_busy,l_valid,l_clip;
    logic [8:0] l_row;
    logic signed [31:0] l_result;
    logic signed [31:0] res1_wide,res2_wide;
    logic signed [15:0] res1_value,res2_value;
    logic res1_clip,res2_clip;
    logic norm_table_valid;

    // Exact residual alignment: first add at the finer exponent, then one RNE.
    function automatic logic signed [31:0] round2(input logic signed [31:0] value);
        logic signed [31:0] base;
        begin base=value>>>2;if(value[1:0]>2 || (value[1:0]==2 && base[0]))base=base+1;round2=base;end
    endfunction
    function automatic logic signed [15:0] clip16(input logic signed [31:0] value);
        clip16=value>32767 ? 16'sh7fff : value< -32768 ? 16'sh8000 : value[15:0];
    endfunction
    assign res1_wide=round2(32'(embedding[o_row[4:0]])+(32'(o_result)<<<2));
    assign res2_wide=round2(32'(residual1[ff_row[4:0]])+(32'(ff_result)<<<2));
    assign res1_value=clip16(res1_wide);assign res2_value=clip16(res2_wide);
    assign res1_clip=res1_wide>32767 || res1_wide< -32768;
    assign res2_clip=res2_wide>32767 || res2_wide< -32768;
    assign observe[0]=cache_read_valid && !cache_read_ready;
    // observe[1] comes from the attention request/response state.
    assign observe[2]=cache_output_valid && cache_output_ready;
    assign phase=state;
    assign busy=state!=IDLE;
    assign front_reset=reset || (clear_context && state==IDLE);
    assign token_ready=configured && state==IDLE && !reset && !clear_context && !weight_valid &&
                       token<320 && context_count<256 && (context_count!=0 || token==256);
    assign logit_valid=(state==LOGIT_WAIT && l_valid) || state==FAULT;
    assign logit_index=state==FAULT ? 9'd0 : l_row;
    assign logit=state==FAULT ? 32'sd0 : l_result;
    assign query_ready=state==FRONT_WAIT && att_load_ready;
    assign att_ready=state==ATT_WAIT && o_input_ready;
    assign o_ready=state==O_WAIT && n2_load_ready;
    assign n1_ready=state==N1_WAIT && front_load_ready;
    assign n2_ready=state==N2_WAIT && ff_input_ready;
    assign ff_ready=state==FF_WAIT && nf_load_ready;
    assign nf_ready=state==NF_WAIT && l_input_ready;
    assign accept_weight=weight_valid && weight_ready;
    // A producer offers valid independently of receiver ready. Feeding the
    // acceptance pulse back into child-valid ports made a combinational loop
    // through their ready/start arbitration after synthesis. The ordered
    // configuration phase runs before any token, so all recipients are idle;
    // broadcast table recipients also apply the same index/value checks.
    assign weight_offer=weight_valid && !reset && !configured && state==IDLE &&
                        !token_valid && !clear_context && weight_bank==next_bank && weight_address==next_word;
    assign norm_table_valid=weight_offer && (weight_bank==13 || weight_bank==14);

    always_comb begin
        case(next_bank)
            0:bank_words=10240;
            1,2,3,4:bank_words=1024;
            5,6,7:bank_words=4096;
            8,9,10:bank_words=32;
            11:bank_words=2048;
            13:bank_words=257;
            14:bank_words=256;
            default:bank_words=0;
        endcase
        case(weight_bank)
            0:load_target_ready=l_weight_ready;
            1,2,3:load_target_ready=front_load_ready;
            4:load_target_ready=o_weight_ready;
            5,6,7:load_target_ready=ff_weight_ready;
            8,9,10:load_target_ready=1;
            11:load_target_ready=front_coeff_ready;
            13:load_target_ready=n1_table_ready && n2_table_ready && nf_table_ready && ff_table_ready && att_table_ready;
            14:load_target_ready=n1_table_ready && n2_table_ready && nf_table_ready;
            default:load_target_ready=0;
        endcase
    end
    assign weight_ready=!reset && !configured && state==IDLE && !token_valid && !clear_context &&
                        weight_bank==next_bank && weight_address==next_word && load_target_ready;

    rmsnorm #(.SOURCE_EXP(-14),.GAIN_EXP(-14),.OUTPUT_EXP(-11)) norm1 (
        .clk(clk),.reset(reset),.load_valid(state==EMBED_LOAD),.load_ready(n1_load_ready),
        .load_address(coordinate),.load_input(embed_value),.load_gain(gain1[coordinate]),
        .start(state==N1_START),.start_ready(n1_start_ready),.busy(n1_busy),
        .table_valid(norm_table_valid),.table_ready(n1_table_ready),.table_kind(weight_bank==14),
        .table_index(weight_address[8:0]),.table_value(weight_value),.result_valid(n1_valid),.result_ready(n1_ready),
        .result_index(n1_index),.result(n1_result),.saturated(n1_clip),.error(n1_error));
    rmsnorm #(.SOURCE_EXP(-12),.GAIN_EXP(-14),.OUTPUT_EXP(-11)) norm2 (
        .clk(clk),.reset(reset),.load_valid(state==O_WAIT && o_valid),.load_ready(n2_load_ready),
        .load_address(o_row[4:0]),.load_input(res1_value),.load_gain(gain2[o_row[4:0]]),
        .start(state==N2_START),.start_ready(n2_start_ready),.busy(n2_busy),
        .table_valid(norm_table_valid),.table_ready(n2_table_ready),.table_kind(weight_bank==14),
        .table_index(weight_address[8:0]),.table_value(weight_value),.result_valid(n2_valid),.result_ready(n2_ready),
        .result_index(n2_index),.result(n2_result),.saturated(n2_clip),.error(n2_error));
    rmsnorm #(.SOURCE_EXP(-10),.GAIN_EXP(-13),.OUTPUT_EXP(-10)) normfinal (
        .clk(clk),.reset(reset),.load_valid(state==FF_WAIT && ff_valid),.load_ready(nf_load_ready),
        .load_address(ff_row[4:0]),.load_input(res2_value),.load_gain(gain3[ff_row[4:0]]),
        .start(state==NF_START),.start_ready(nf_start_ready),.busy(nf_busy),
        .table_valid(norm_table_valid),.table_ready(nf_table_ready),.table_kind(weight_bank==14),
        .table_index(weight_address[8:0]),.table_value(weight_value),.result_valid(nf_valid),.result_ready(nf_ready),
        .result_index(nf_index),.result(nf_result),.saturated(nf_clip),.error(nf_error));
    frontend front (
        .clk(clk),.reset(front_reset),.load_valid((weight_offer && weight_bank>=1 && weight_bank<=3) || (state==N1_WAIT && n1_valid)),
        .load_ready(front_load_ready),.load_address(state==N1_WAIT ? n1_index : weight_address[4:0]),
        .load_row(state==N1_WAIT ? 7'd0 : 7'((int'(weight_bank)-1)*32+int'(weight_address[9:5]))),
        .load_input(state==N1_WAIT ? n1_result : 16'sd0),
        .load_weight(state==N1_WAIT ? q_first_row[n1_index] : weight_value[15:0]),
        .coefficient_valid(weight_offer && weight_bank==11),.coefficient_ready(front_coeff_ready),
        .coefficient_position(weight_address[10:3]),.coefficient_pair(weight_address[2:0]),
        .load_cosine(weight_value[15:0]),.load_sine(weight_value[31:16]),
        .start(state==FRONT_START),.token_position(context_count),.start_ready(front_start_ready),.busy(front_busy),
        .query_valid(query_valid),.query_ready(query_ready),.query_coordinate(query_coordinate),.query_value(query_value),.saturated(front_clip),
        .read_valid(cache_read_valid),.read_ready(cache_read_ready),.read_position(cache_read_position),.read_coordinate(cache_read_coordinate),
        .output_valid(cache_output_valid),.output_ready(cache_output_ready),.output_position(cache_output_position),
        .output_coordinate(cache_output_coordinate),.output_k(cache_k),.output_v(cache_v),.token_count(context_count));
    attention att (
        .clk(clk),.reset(reset),.load_valid(state==FRONT_WAIT && query_valid),.load_ready(att_load_ready),
        .load_index(query_coordinate),.load_value(query_value),
        .table_valid(weight_offer && weight_bank==13),.table_ready(att_table_ready),.table_index(weight_address[8:0]),.table_value(weight_value),
        .start(state==ATT_START),.start_ready(att_start_ready),.busy(att_busy),.context_length(context_count),
        .cache_read_valid(cache_read_valid),.cache_read_ready(cache_read_ready),.cache_read_position(cache_read_position),.cache_read_coordinate(cache_read_coordinate),
        .cache_output_valid(cache_output_valid),.cache_output_ready(cache_output_ready),.cache_output_position(cache_output_position),
        .cache_output_coordinate(cache_output_coordinate),.cache_output_k(cache_k),.cache_output_v(cache_v),
        .result_valid(att_valid),.result_ready(att_ready),.result_index(att_index),.result(att_result),.saturated(att_clip),.error(att_error),
        .observe_cache_wait(observe[1]),
        .score_valid(),.score_head(),.score_position(),.score_value(),
        .exp_valid(),.exp_head(),.exp_position(),.exp_value(),
        .probability_valid(),.probability_head(),.probability_position(),.probability_value(),
        .step_valid(),.step_mode(),.step_head(),.step_position(),.step_coordinate(),
        .step_input(),.step_weight(),.step_product(),.step_sum());
    dense #(.INPUTS(32),.OUTPUTS(32),.SHIFT(16),.RESULT_BITS(16)) output_projection (
        .clk(clk),.reset(reset),.input_valid(state==ATT_WAIT && att_valid),.input_ready(o_input_ready),
        .input_address({3'd0,att_index}),.input_value(att_result),
        .weight_valid(weight_offer && weight_bank==4),.weight_ready(o_weight_ready),.weight_row({4'd0,weight_address[9:5]}),
        .weight_address({3'd0,weight_address[4:0]}),.weight_value(weight_value[15:0]),
        .start(state==O_START),.start_ready(o_start_ready),.busy(o_busy),.result_valid(o_valid),.result_ready(o_ready),
        .result_row(o_row),.result(o_result),.saturated(o_clip),
        .step_valid(),.step_index(),.step_row(),.step_input(),.step_weight(),.step_product(),.step_sum());
    feedforward ff (
        .clk(clk),.reset(reset),.input_valid(state==N2_WAIT && n2_valid),.input_ready(ff_input_ready),
        .input_address({3'd0,n2_index}),.input_value(n2_result),
        .weight_valid(weight_offer && weight_bank>=5 && weight_bank<=7),.weight_ready(ff_weight_ready),
        .weight_bank(2'(weight_bank-5)),.weight_row(weight_bank==7 ? {4'd0,weight_address[11:7]} : {2'd0,weight_address[11:5]}),
        .weight_address(weight_bank==7 ? {1'b0,weight_address[6:0]} : {3'd0,weight_address[4:0]}),.weight_value(weight_value[15:0]),
        .table_valid(weight_offer && weight_bank==13),.table_ready(ff_table_ready),.table_index(weight_address[8:0]),.table_value(weight_value),
        .start(state==FF_START),.start_ready(ff_start_ready),.busy(ff_busy),.result_valid(ff_valid),.result_ready(ff_ready),
        .result_row(ff_row),.result(ff_result),.saturated(ff_clip),.error(ff_error),
        .observe_ff(observe[5:3]),
        .element_valid(ff_element_valid),.element_index(ff_element_index),.element_gate(ff_element_gate),.element_up(ff_element_up),
        .element_silu(ff_element_silu),.element_hidden(ff_element_hidden),.element_saturated(ff_element_clip));
    dense #(.INPUTS(32),.OUTPUTS(320),.SHIFT(8),.RESULT_BITS(32)) logits (
        .clk(clk),.reset(reset),.input_valid(state==NF_WAIT && nf_valid),.input_ready(l_input_ready),
        .input_address({3'd0,nf_index}),.input_value(nf_result),
        .weight_valid(weight_offer && weight_bank==0),.weight_ready(l_weight_ready),.weight_row(weight_address[13:5]),
        .weight_address({3'd0,weight_address[4:0]}),.weight_value(weight_value[15:0]),
        .start(state==LOGIT_START),.start_ready(l_start_ready),.busy(l_busy),.result_valid(l_valid),.result_ready(state==LOGIT_WAIT && logit_ready),
        .result_row(l_row),.result(l_result),.saturated(l_clip),
        .step_valid(),.step_index(),.step_row(),.step_input(),.step_weight(),.step_product(),.step_sum());

    always_ff @(posedge clk) begin
        if(accept_weight)begin
            if(weight_bank==0)embedding_memory[weight_address[13:0]]<=weight_value[15:0];
            if(weight_bank==1 && weight_address<32)q_first_row[weight_address[4:0]]<=weight_value[15:0];
            if(weight_bank==8)gain1[weight_address[4:0]]<=weight_value[15:0];
            if(weight_bank==9)gain2[weight_address[4:0]]<=weight_value[15:0];
            if(weight_bank==10)gain3[weight_address[4:0]]<=weight_value[15:0];
        end
        if(reset)begin state<=IDLE;next_bank<=0;next_word<=0;configured<=0;current_token<=0;coordinate<=0;embed_value<=0;saturated<=0;error<=0;end
        else begin
            if(ff_element_valid)saturated<=saturated || (|ff_element_clip);
            if(accept_weight)begin
                if(next_word==bank_words-1)begin
                    next_word<=0;
                    if(next_bank==14)configured<=1;
                    else next_bank<=next_bank==11 ? 4'd13 : next_bank+1'b1;
                end else next_word<=next_word+1'b1;
            end
            if((n1_valid && n1_error)||(n2_valid && n2_error)||(nf_valid && nf_error)||(att_valid && att_error)||(ff_valid && ff_error))begin
                error<=1;state<=FAULT;
            end else case(state)
                IDLE: if(token_valid && token_ready)begin current_token<=token;coordinate<=0;saturated<=0;error<=0;state<=EMBED_READ;end
                EMBED_READ: begin embed_value<=embedding_memory[{current_token,coordinate}];state<=EMBED_LOAD;end
                EMBED_LOAD: if(n1_load_ready)begin
                    embedding[coordinate]<=embed_value;
                    if(coordinate==31)state<=N1_START;
                    else begin coordinate<=coordinate+1'b1;state<=EMBED_READ;end
                end
                N1_START: if(n1_start_ready)state<=N1_WAIT;
                N1_WAIT: if(n1_valid && n1_ready)begin saturated<=saturated||n1_clip;if(n1_index==31)state<=FRONT_START;end
                FRONT_START: if(front_start_ready)state<=FRONT_WAIT;
                FRONT_WAIT: if(query_valid && query_ready)begin saturated<=saturated||front_clip;if(query_coordinate==31)state<=ATT_START;end
                ATT_START: if(att_start_ready)state<=ATT_WAIT;
                ATT_WAIT: if(att_valid && att_ready)begin saturated<=saturated||att_clip;if(att_index==31)state<=O_START;end
                O_START: if(o_start_ready)state<=O_WAIT;
                O_WAIT: if(o_valid && o_ready)begin
                    residual1[o_row[4:0]]<=res1_value;saturated<=saturated||o_clip||res1_clip;
                    if(o_row==31)state<=N2_START;
                end
                N2_START: if(n2_start_ready)state<=N2_WAIT;
                N2_WAIT: if(n2_valid && n2_ready)begin saturated<=saturated||n2_clip;if(n2_index==31)state<=FF_START;end
                FF_START: if(ff_start_ready)state<=FF_WAIT;
                FF_WAIT: if(ff_valid && ff_ready)begin saturated<=saturated||ff_clip||res2_clip;if(ff_row==31)state<=NF_START;end
                NF_START: if(nf_start_ready)state<=NF_WAIT;
                NF_WAIT: if(nf_valid && nf_ready)begin saturated<=saturated||nf_clip;if(nf_index==31)state<=LOGIT_START;end
                LOGIT_START: if(l_start_ready)state<=LOGIT_WAIT;
                LOGIT_WAIT: if(l_valid && logit_ready)begin saturated<=saturated||l_clip;if(l_row==319)state<=IDLE;end
                FAULT: begin end // Requires reset/reload; never silently continue a corrupt context.
                default:begin state<=FAULT;error<=1;end
            endcase
        end
    end
endmodule
