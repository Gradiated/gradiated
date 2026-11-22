// Observe each completed position while the unchanged request oracle runs.
int observation_file, observed_position;
int down_ticks[5], down_stalls, ff_ticks;

initial begin
    observation_file = $fopen("down-profile.txt", "w");
    if (!observation_file) $fatal(1, "Cannot open down-projection profile");
end

always @(posedge aclk) if (aresetn && observing && int'(dut.core_phase)==14) begin
    int state_code;
    state_code = int'(dut.core.ff.down_dense.state);
    if (state_code < 0 || state_code > 4) $fatal(1, "Unexpected down state");
    ff_ticks++;
    down_ticks[state_code]++;
    if (dut.core.ff.d_valid && !dut.core.ff.d_ready) down_stalls++;
    if (dut.core.ff.result_valid && dut.core.ff.result_ready && dut.core.ff.result_row==9'd31) begin
        observed_position++;
        $fwrite(observation_file,"%0d %0d %0d %0d %0d %0d %0d\n",observed_position,ff_ticks,
                down_ticks[1],down_ticks[2],down_ticks[3],down_ticks[4],down_stalls);
        foreach (down_ticks[i]) down_ticks[i]=0;
        down_stalls=0;
        ff_ticks=0;
    end
end

final $fclose(observation_file);
