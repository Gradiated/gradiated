// Observe the same ready-cache replay as Experiment 10 and count arithmetic separately.
integer divide_file;
integer full_exps, exp_cycles, prob_cycles;
initial begin
    divide_file=$fopen("attention-divider.txt","w");
    if (!divide_file) $fatal(1,"Cannot open attention divider capture");
    full_exps=0;
    exp_cycles=0;
    prob_cycles=0;
end
always @(posedge aclk) if(aresetn && observing && int'(dut.core_phase)==8) begin
    if(dut.core.att.state==dut.core.att.EXP_SEND && dut.core.att.scalar_cmd_ready &&
       dut.core.att.scalar_a>=-64'sd1048576) full_exps++;
    if(dut.core.att.scalar.state==dut.core.att.scalar.DIV_STEP) begin
        if(dut.core.att.state==dut.core.att.EXP_WAIT) exp_cycles++;
        if(dut.core.att.state==dut.core.att.PROB_WAIT) prob_cycles++;
    end
    if(dut.core.att.result_valid && dut.core.att.result_ready && dut.core.att.result_index==5'd31) begin
        $fwrite(divide_file,"%0d %0d %0d %0d\n",dut.core.att.length,full_exps,exp_cycles,prob_cycles);
        full_exps=0;
        exp_cycles=0;
        prob_cycles=0;
    end
end
final begin
    if(full_exps || exp_cycles || prob_cycles) $fatal(1,"Incomplete attention divider capture");
    $fclose(divide_file);
end
