// Simulation-only measurement of the unchanged full-model attention schedule.
integer attention_profile_file, attention_position;
integer attention_ticks[18];
integer attention_score_request_wait, attention_score_response_wait;
integer attention_value_request_wait, attention_value_response_wait;
integer attention_exp_cutoffs, attention_exp_divide_ticks;
integer attention_zero_probabilities, attention_prob_divide_ticks, attention_zero_prob_divide_ticks;
integer attention_scalar_send_wait, attention_output_wait;

task automatic reset_attention_counters();
    foreach (attention_ticks[i]) attention_ticks[i] = 0;
    attention_score_request_wait = 0;
    attention_score_response_wait = 0;
    attention_value_request_wait = 0;
    attention_value_response_wait = 0;
    attention_exp_cutoffs = 0;
    attention_exp_divide_ticks = 0;
    attention_zero_probabilities = 0;
    attention_prob_divide_ticks = 0;
    attention_zero_prob_divide_ticks = 0;
    attention_scalar_send_wait = 0;
    attention_output_wait = 0;
endtask

initial begin
    attention_position = 0;
    reset_attention_counters();
    attention_profile_file = $fopen("attention-profile.txt", "w");
    if (!attention_profile_file) $fatal(1, "Cannot open attention profile");
end

always @(posedge aclk) if (aresetn && observing && int'(dut.core_phase) == 8) begin
    integer state_code;
    state_code = int'(dut.core.att.state);
    if (state_code < 0 || state_code >= 18) $fatal(1, "Unexpected attention state");
    attention_ticks[state_code]++;
    case (state_code)
        1: if (!dut.core.att.cache_read_ready) attention_score_request_wait++;
        2: if (!dut.core.att.cache_output_valid) attention_score_response_wait++;
        7: if (dut.core.att.scalar_cmd_ready && dut.core.att.scalar_a < -64'sd1048576)
            attention_exp_cutoffs++;
        8: if (dut.core.att.scalar.state == 5'd2)
            attention_exp_divide_ticks++;
        10: if (dut.core.att.scalar_cmd_ready && dut.core.att.scalar_a == 0)
            attention_zero_probabilities++;
        11: if (dut.core.att.scalar.state == 5'd2) begin
            attention_prob_divide_ticks++;
            if (dut.core.att.scalar_a == 0) attention_zero_prob_divide_ticks++;
        end
        12: if (!dut.core.att.cache_read_ready) attention_value_request_wait++;
        13: if (!dut.core.att.cache_output_valid) attention_value_response_wait++;
        17: if (!dut.core.att.result_ready) attention_output_wait++;
        default: ;
    endcase
    if (dut.core.att.scalar_cmd_valid && !dut.core.att.scalar_cmd_ready) attention_scalar_send_wait++;
    if (dut.core.att.result_valid && dut.core.att.result_ready && dut.core.att.result_index == 5'd31) begin
        attention_position++;
        $fwrite(attention_profile_file, "%0d %0d", attention_position, dut.core.att.length);
        foreach (attention_ticks[i]) $fwrite(attention_profile_file, " %0d", attention_ticks[i]);
        $fwrite(attention_profile_file, " %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\n",
            attention_score_request_wait, attention_score_response_wait, attention_value_request_wait,
            attention_value_response_wait, attention_exp_cutoffs, attention_exp_divide_ticks,
            attention_zero_probabilities, attention_prob_divide_ticks, attention_zero_prob_divide_ticks,
            attention_scalar_send_wait, attention_output_wait);
        reset_attention_counters();
    end
end

final begin
    foreach (attention_ticks[i])
        if (attention_ticks[i] != 0) $fatal(1, "Incomplete attention observation");
    $fclose(attention_profile_file);
end
