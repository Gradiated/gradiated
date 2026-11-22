// Simulation-only accounting of the accepted lookahead requests and serial boundary reads.
integer cache_profile_file;
integer cache_schedule[8];
initial begin
    foreach (cache_schedule[i]) cache_schedule[i]=0;
    cache_profile_file=$fopen("overlap-profile.txt","w");
    if (!cache_profile_file) $fatal(1,"Cannot open cache overlap profile");
end
always @(posedge aclk) if(aresetn && observing && int'(dut.core_phase)==8) begin
    int att_state;
    att_state=int'(dut.core.att.state);
    if ((dut.core.att.cache_read_valid && !dut.core.att.cache_read_ready) ||
        (dut.core.att.cache_output_ready && !dut.core.att.cache_output_valid))
        $fatal(1,"Replay departed from preregistered ready-cache schedule");
    case(att_state)
        1: cache_schedule[0]++;
        2: cache_schedule[1]++;
        3: begin
            cache_schedule[2]++;
            if(dut.core.att.cache_read_valid) cache_schedule[3]++;
        end
        12: cache_schedule[4]++;
        13: cache_schedule[5]++;
        14: begin
            cache_schedule[6]++;
            if(dut.core.att.cache_read_valid) cache_schedule[7]++;
        end
        default: ;
    endcase
    if(dut.core.att.result_valid && dut.core.att.result_ready && dut.core.att.result_index==5'd31) begin
        $fwrite(cache_profile_file,"%0d",dut.core.att.length);
        foreach(cache_schedule[i]) $fwrite(cache_profile_file," %0d",cache_schedule[i]);
        $fwrite(cache_profile_file,"\n");
        foreach(cache_schedule[i]) cache_schedule[i]=0;
    end
end
final $fclose(cache_profile_file);
