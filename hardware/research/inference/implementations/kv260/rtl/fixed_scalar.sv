// Serial checked integer helpers for the selected fixed.py arithmetic.
// No floating point, division operator, or wide combinational multiplier.
// Lookup tables are data loaded by the caller, not learned substitute values.
`timescale 1ns/1ps
module fixed_scalar (
    input logic clk, reset,
    input logic cmd_valid,
    output logic cmd_ready,
    input logic [2:0] cmd_op,
    input logic signed [63:0] cmd_a, cmd_b,
    input logic signed [7:0] cmd_shift,
    input logic table_valid,
    output logic table_ready,
    input logic table_kind,
    input logic [8:0] table_index,
    input logic [31:0] table_value,
    output logic result_valid,
    input logic result_ready,
    output logic signed [63:0] result,
    output logic signed [7:0] result_exponent,
    output logic error
);
    localparam logic [2:0] OP_SHIFT=0, OP_DIV=1, OP_MUL=2, OP_EXP=3, OP_RSQRT=4;
    localparam logic [63:0] SIGNED_MAX=64'h7fff_ffff_ffff_ffff;
    typedef enum logic [4:0] {
        IDLE, OUTPUT, DIV_STEP, MUL_STEP, SIMPLE_DONE,
        EXP_POWER, EXP_INDEX, EXP_LOAD, EXP_MUL, EXP_INTERP, EXP_DONE,
        RSQ_INDEX, RSQ_LOAD, RSQ_YY, RSQ_MY, RSQ_FACTOR, RSQ_UPDATE
    } state_t;
    state_t state, return_state;
    logic [31:0] exp_memory[0:256], rsqrt_memory[0:255];
    logic [256:0] exp_loaded;
    logic [255:0] rsqrt_loaded;
    logic signed [63:0] math_value;
    logic negative, rounding;
    logic [6:0] remaining;
    logic [63:0] numerator, denominator, quotient;
    logic [64:0] remainder, trial_remainder, next_remainder, rounded_quotient;
    logic [63:0] next_quotient;
    logic [127:0] multiplicand, product_sum, next_product;
    logic [63:0] multiplier;
    logic [7:0] power;
    logic [63:0] fraction;
    logic [8:0] index;
    logic [31:0] exp_first, exp_second;
    logic signed [63:0] m, y;
    logic signed [7:0] exponent;
    logic iteration;

    assign cmd_ready=state==IDLE && !reset && !table_valid;
    assign table_ready=state==IDLE && !reset && !cmd_valid &&
        ((!table_kind && table_index<=256 && table_value<=32'h8000_0000) ||
         (table_kind && table_index<256 && table_value>0 && table_value<=32'h4000_0000));
    assign result_valid=state==OUTPUT && !reset;

    function automatic logic [63:0] magnitude(input logic signed [63:0] value);
        magnitude=value[63] ? (~$unsigned(value)+64'd1) : $unsigned(value);
    endfunction
    function automatic logic signed [63:0] shift_right_even(
        input logic signed [63:0] value, input logic [7:0] amount
    );
        logic signed [63:0] base;
        logic [63:0] low, half, mask;
        begin
            if(amount==0)shift_right_even=value;
            else if(amount>=64)shift_right_even=0;
            else begin
                mask=(64'd1<<amount)-64'd1;
                half=64'd1<<(amount-8'd1);
                low=$unsigned(value)&mask;
                base=value>>>amount;
                if(low>half || (low==half && base[0]))base=base+64'sd1;
                shift_right_even=base;
            end
        end
    endfunction
    function automatic integer top_bit(input logic [63:0] value);
        integer i;
        begin
            top_bit=0;
            for(i=0;i<63;i=i+1)if(value[i])top_bit=i;
        end
    endfunction

    always_comb begin
        trial_remainder={remainder[63:0],numerator[63]};
        next_remainder=trial_remainder;
        next_quotient={quotient[62:0],1'b0};
        if(trial_remainder>={1'b0,denominator})begin
            next_remainder=trial_remainder-{1'b0,denominator};
            next_quotient[0]=1;
        end
        rounded_quotient={1'b0,next_quotient};
        if(rounding && (next_remainder>({1'b0,denominator}-next_remainder) ||
           (next_remainder==({1'b0,denominator}-next_remainder) && next_quotient[0])))
            rounded_quotient=rounded_quotient+65'd1;
        next_product=product_sum+(multiplier[0] ? multiplicand : 128'd0);
    end

    task automatic reject;
        begin result<=0;result_exponent<=0;error<=1;state<=OUTPUT;end
    endtask
    task automatic divide_start(input logic signed [63:0] a,
        input logic [63:0] b,input logic round_even,input state_t resume_state);
        begin
            negative<=a[63];rounding<=round_even;numerator<=magnitude(a);
            denominator<=b;quotient<=0;remainder<=0;remaining<=64;
            return_state<=resume_state;state<=DIV_STEP;
        end
    endtask
    task automatic multiply_start(input logic signed [63:0] a,
        input logic signed [63:0] b,input state_t resume_state);
        begin
            negative<=a[63]^b[63];multiplicand<={64'd0,magnitude(a)};
            multiplier<=magnitude(b);product_sum<=0;remaining<=64;
            return_state<=resume_state;state<=MUL_STEP;
        end
    endtask

    always_ff @(posedge clk) begin
        if(!reset && table_valid && table_ready)begin
            if(table_kind)rsqrt_memory[table_index[7:0]]<=table_value;
            else exp_memory[table_index]<=table_value;
        end
        if(reset)begin
            state<=IDLE;result<=0;result_exponent<=0;error<=0;
            exp_loaded<='0;rsqrt_loaded<='0;
            math_value<=0;negative<=0;rounding<=0;remaining<=0;
            numerator<=0;denominator<=0;quotient<=0;remainder<=0;
            multiplicand<=0;multiplier<=0;product_sum<=0;
            power<=0;fraction<=0;index<=0;exp_first<=0;exp_second<=0;
            m<=0;y<=0;exponent<=0;iteration<=0;return_state<=IDLE;
        end else begin
            if(table_valid && table_ready)begin
                if(table_kind)rsqrt_loaded[table_index[7:0]]<=1;
                else exp_loaded[table_index]<=1;
            end
            case(state)
                IDLE: if(cmd_valid && cmd_ready)begin
                    error<=0;result_exponent<=0;
                    case(cmd_op)
                        OP_SHIFT: begin
                            if(cmd_shift>=0)begin
                                if(cmd_shift>62 || magnitude(cmd_a)>(SIGNED_MAX>>cmd_shift))reject();
                                else begin result<=cmd_a<<<cmd_shift;state<=OUTPUT;end
                            end else begin
                                result<=shift_right_even(cmd_a,$unsigned(-cmd_shift));state<=OUTPUT;
                            end
                        end
                        OP_DIV: begin
                            if(cmd_b<=0 || $unsigned(cmd_b)>64'h4000_0000_0000_0000)reject();
                            else divide_start(cmd_a,$unsigned(cmd_b),1,SIMPLE_DONE);
                        end
                        OP_MUL: multiply_start(cmd_a,cmd_b,SIMPLE_DONE);
                        OP_EXP: begin
                            if(cmd_a>0 || cmd_a< -64'sh4000_0000_0000_0000)reject();
                            else if(cmd_a< -64'sd1048576)begin result<=0;state<=OUTPUT;end
                            else divide_start(-cmd_a,64'd45426,0,EXP_POWER);
                        end
                        OP_RSQRT: begin
                            if(cmd_a<=0)reject();
                            else begin
                                exponent<=8'((top_bit($unsigned(cmd_a))-32)>>>1);
                                // Scale to Q2.30. The right shift is the only
                                // rounding here; a left shift fits in 33 bits.
                                if((-2-2*((top_bit($unsigned(cmd_a))-32)>>>1))>=0)
                                    m<=cmd_a<<<(-2-2*((top_bit($unsigned(cmd_a))-32)>>>1));
                                else m<=shift_right_even(cmd_a,8'(2+2*((top_bit($unsigned(cmd_a))-32)>>>1)));
                                iteration<=0;state<=RSQ_INDEX;
                            end
                        end
                        default:reject();
                    endcase
                end
                DIV_STEP: begin
                    numerator<={numerator[62:0],1'b0};quotient<=next_quotient;remainder<=next_remainder;
                    remaining<=remaining-7'd1;
                    if(remaining==1)begin
                        if(rounded_quotient>(negative ? 65'h08000_0000_0000_0000 : {1'b0,SIGNED_MAX}))reject();
                        else begin
                            math_value<=negative ? -$signed(rounded_quotient[63:0]) : $signed(rounded_quotient[63:0]);
                            state<=return_state;
                        end
                    end
                end
                MUL_STEP: begin
                    product_sum<=next_product;multiplicand<=multiplicand<<1;multiplier<=multiplier>>1;
                    remaining<=remaining-7'd1;
                    if(remaining==1)begin
                        if(next_product>{64'd0,SIGNED_MAX})reject();
                        else begin
                            math_value<=negative ? -$signed(next_product[63:0]) : $signed(next_product[63:0]);
                            state<=return_state;
                        end
                    end
                end
                SIMPLE_DONE: begin result<=math_value;state<=OUTPUT;end
                EXP_POWER: begin
                    power<=math_value[7:0];
                    divide_start($signed({remainder[55:0],8'd0}),64'd45426,0,EXP_INDEX);
                end
                EXP_INDEX: begin
                    index<=math_value[8:0];fraction<=remainder[63:0];state<=EXP_LOAD;
                end
                EXP_LOAD: begin
                    if(index>255 || !exp_loaded[index] || !exp_loaded[index+9'd1])reject();
                    else begin exp_first<=exp_memory[index];exp_second<=exp_memory[index+9'd1];state<=EXP_MUL;end
                end
                EXP_MUL: multiply_start($signed({32'd0,exp_second})-$signed({32'd0,exp_first}),$signed(fraction),EXP_INTERP);
                EXP_INTERP: divide_start(math_value,64'd45426,1,EXP_DONE);
                EXP_DONE: begin
                    result<=shift_right_even($signed({32'd0,exp_first})+math_value,power);state<=OUTPUT;
                end
                RSQ_INDEX: begin
                    if(m==64'sh1_0000_0000)begin
                        m<=m>>>2;exponent<=exponent+8'sd1;
                        divide_start(0,64'shC000_0000,0,RSQ_LOAD);
                    end else divide_start((m-64'sh4000_0000)<<<8,64'shC000_0000,0,RSQ_LOAD);
                end
                RSQ_LOAD: begin
                    if(math_value<0 || math_value>255 || !rsqrt_loaded[math_value[7:0]])reject();
                    else begin y<=$signed({32'd0,rsqrt_memory[math_value[7:0]]});state<=RSQ_YY;end
                end
                RSQ_YY: multiply_start(y,y,RSQ_MY);
                RSQ_MY: begin
                    multiply_start(m,shift_right_even(math_value,30),RSQ_FACTOR);
                end
                RSQ_FACTOR: multiply_start(y,64'shC000_0000-shift_right_even(math_value,30),RSQ_UPDATE);
                RSQ_UPDATE: begin
                    y<=shift_right_even(math_value,31);
                    if(iteration)begin
                        result<=shift_right_even(math_value,31);result_exponent<=exponent;state<=OUTPUT;
                    end else begin iteration<=1;state<=RSQ_YY;end
                end
                OUTPUT: if(result_ready)state<=IDLE;
                default:state<=IDLE;
            endcase
        end
    end
endmodule
