// Record ordered numerical events and per-position exponential occupancy.
integer pair_events, pair_profile;
integer exp_window, launches, singles, lane0_cycles, lane1_cycles, both_cycles;
integer short0, short1;

initial begin
    pair_events = $fopen("attention-events.txt", "w");
    pair_profile = $fopen("attention-pairs.txt", "w");
    if (!pair_events || !pair_profile) $fatal(1, "No attention output files");
end

always @(posedge aclk) if (aresetn && observing && int'(dut.core_phase)==8) begin
    bit first_busy, second_busy;
    first_busy = dut.core.att.state==dut.core.att.EXP_WAIT && !dut.core.att.scalar_result_valid;
    second_busy = (dut.core.att.state==dut.core.att.EXP_WAIT ||
                   dut.core.att.state==dut.core.att.EXP_RETIRE_SECOND) &&
                   !dut.core.att.second_result_valid &&
                   dut.core.att.second_exp.state!=dut.core.att.second_exp.IDLE;
    if (first_busy) lane0_cycles++;
    if (second_busy) lane1_cycles++;
    if (first_busy && second_busy) both_cycles++;
    if (dut.core.att.state==dut.core.att.EXP_READ ||
        dut.core.att.state==dut.core.att.EXP_READ_SECOND ||
        dut.core.att.state==dut.core.att.EXP_SEND ||
        dut.core.att.state==dut.core.att.EXP_WAIT ||
        dut.core.att.state==dut.core.att.EXP_RETIRE_SECOND) exp_window++;
    if (dut.core.att.state==dut.core.att.EXP_SEND &&
        dut.core.att.scalar_cmd_valid && dut.core.att.scalar_cmd_ready) begin
        if (dut.core.att.scalar_a < -64'sd1048576) short0++;
        if (dut.core.att.exp_pair) begin
            if (!dut.core.att.second_cmd_valid || !dut.core.att.second_cmd_ready)
                $fatal(1, "Second exponential did not start with the first");
            launches++;
            if (dut.core.att.second_input < -64'sd1048576) short1++;
        end else singles++;
    end
    if (dut.core.att.score_valid)
        $fwrite(pair_events,"S %0d %0d %0d\n",dut.core.att.score_head,dut.core.att.score_position,
                dut.core.att.score_value);
    if (dut.core.att.exp_valid)
        $fwrite(pair_events,"E %0d %0d %0d %0d\n",dut.core.att.exp_head,dut.core.att.exp_position,
                dut.core.att.exp_value,dut.core.att.exp_sum);
    if (dut.core.att.probability_valid)
        $fwrite(pair_events,"P %0d %0d %0d\n",dut.core.att.probability_head,
                dut.core.att.probability_position,dut.core.att.probability_value);
    if (dut.core.att.result_valid && dut.core.att.result_ready && dut.core.att.result_index==5'd31) begin
        $fwrite(pair_profile,"%0d %0d %0d %0d %0d %0d %0d %0d %0d\n",dut.core.att.length,exp_window,
                launches,singles,lane0_cycles,lane1_cycles,both_cycles,short0,short1);
        exp_window=0;launches=0;singles=0;lane0_cycles=0;lane1_cycles=0;both_cycles=0;short0=0;short1=0;
    end
end
final begin
    if (exp_window || launches || singles) $fatal(1, "Incomplete attention-pair capture");
    $fclose(pair_events);
    $fclose(pair_profile);
end
