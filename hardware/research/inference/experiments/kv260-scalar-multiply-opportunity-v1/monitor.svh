// Count the scalar recurrence only while the model is inside the relevant
// enclosing phase. Origins 0, 1 and 2 are direct, exponential and reciprocal root.
integer multiply_calls[6][3], multiply_cycles[6][3];
integer multiply_a_width[6][3], multiply_b_width[6][3];
longint unsigned multiply_digest[6][3];
integer simultaneous_attention_multiply_cycles = 0;

function automatic integer bit_width(input logic [63:0] value);
    for (int i=63; i>=0; i--)
        if (value[i]) return i+1;
    return 0;
endfunction

task automatic observe_multiply(input int unit, resume,
        input logic [6:0] left, input int latency,
        input logic [63:0] a,b, input logic [127:0] product, input logic negative);
    int origin;
    case(resume)
        4: origin=0;       // SIMPLE_DONE
        9: origin=1;       // EXP_INTERP
        14,15,16: origin=2;// RSQ_MY, RSQ_FACTOR, RSQ_UPDATE
        default: begin
            $fatal(1, "Unexpected scalar resume state %0d", resume);
            origin=0;
        end
    endcase
    multiply_cycles[unit][origin]++;
    if (int'(left)==latency) begin
        if (bit_width(a)>multiply_a_width[unit][origin]) multiply_a_width[unit][origin]=bit_width(a);
        if (bit_width(b)>multiply_b_width[unit][origin]) multiply_b_width[unit][origin]=bit_width(b);
        multiply_digest[unit][origin]=(multiply_digest[unit][origin]^a)*64'h100000001b3;
        multiply_digest[unit][origin]=(multiply_digest[unit][origin]^b)*64'h100000001b3;
        multiply_digest[unit][origin]=(multiply_digest[unit][origin]^64'(negative))*64'h100000001b3;
    end
    if (left==1) begin
        multiply_calls[unit][origin]++;
        multiply_digest[unit][origin]=(multiply_digest[unit][origin]^product[127:64])*64'h100000001b3;
        multiply_digest[unit][origin]=(multiply_digest[unit][origin]^product[63:0])*64'h100000001b3;
    end
endtask

always @(posedge aclk) if (aresetn && observing) begin
        // SCALAR_HOOKS
        if (dut.core_phase==8 && dut.core.att.scalar.state==dut.core.att.scalar.MUL_STEP &&
            dut.core.att.second_exp.state==dut.core.att.second_exp.MUL_STEP)
            simultaneous_attention_multiply_cycles++;
end

final begin
    int monitor_file;
    monitor_file=$fopen("multiply-profile.txt","w");
    if (!monitor_file) $fatal(1, "Cannot open multiply profile");
    for (int unit=0; unit<6; unit++)
        for (int origin=0; origin<3; origin++)
            $fwrite(monitor_file,"%0d %0d %0d %0d %0d %0d %016x\n",unit,origin,
                    multiply_calls[unit][origin],multiply_cycles[unit][origin],
                    multiply_a_width[unit][origin],multiply_b_width[unit][origin],
                    multiply_digest[unit][origin]);
    $fwrite(monitor_file,"%0d\n",simultaneous_attention_multiply_cycles);
    $fclose(monitor_file);
end
