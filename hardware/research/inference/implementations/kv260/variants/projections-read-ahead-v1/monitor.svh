// Assert ordered read issue/retire coordinates and count all four projection lanes.
integer pr_profile, pr_outputs, pr_pairs;
integer pr_depth[4], pr_reads[4], pr_mac[4], pr_round[4], pr_holds[4], pr_issues[4], pr_steps[4], pr_rows[4];
integer pr_ff_depth, pr_ff_wait, pr_first_pair_wait, pr_later_pair_wait;
logic [2:0] pr_state[4];
logic [8:0] pr_row[4], pr_consumed_row[4], pr_step_row[4];
logic [7:0] pr_address[4], pr_step_index[4];
logic pr_advance[4], pr_valid[4], pr_ready[4], pr_clipped[4], pr_step[4];
logic signed [15:0] pr_result[4];

// PROJECTION_CONNECTIONS

initial begin
    pr_profile=$fopen("projection-profile.txt","w");
    pr_outputs=$fopen("projection-outputs.txt","w");
    pr_pairs=$fopen("projection-gate-up-wait.txt","w");
    if (pr_profile==0 || pr_outputs==0 || pr_pairs==0)
        $fatal(1,"Cannot open projection replay traces");
end

always @(posedge aclk) if (aresetn && observing) begin
    for (int lane=0; lane<4; lane++) begin
        int nrows;
        nrows=lane==0 ? 96 : lane==1 ? 32 : 128;
        if (pr_state[lane]==3'd1) pr_reads[lane]++;
        if (pr_state[lane]==3'd2) pr_mac[lane]++;
        if (pr_state[lane]==3'd3) pr_round[lane]++;
        if (pr_state[lane]==3'd1 || pr_advance[lane]) begin
            if (int'(pr_row[lane])!=pr_issues[lane]/32 || int'(pr_address[lane])!=pr_issues[lane]%32 ||
                pr_issues[lane]>=32*nrows)
                $fatal(1,"Projection %0d next read wrapped, repeated or reordered across rows",lane);
            pr_issues[lane]++;
        end
        if (pr_step[lane]) begin
            if (int'(pr_step_index[lane])!=pr_steps[lane]%32 || int'(pr_step_row[lane])!=pr_steps[lane]/32 ||
                pr_steps[lane]>=32*nrows || pr_steps[lane]>=pr_issues[lane])
                $fatal(1,"Projection %0d retired the wrong operand coordinate",lane);
            pr_steps[lane]++;
        end
        if (pr_valid[lane] && !pr_ready[lane]) pr_holds[lane]++;
        if (pr_valid[lane] && pr_ready[lane]) begin
            if (int'(pr_consumed_row[lane])!=pr_rows[lane] || pr_steps[lane]!=32*(pr_rows[lane]+1))
                $fatal(1,"Projection %0d retired a row too early or out of order",lane);
            $fwrite(pr_outputs,"%0d %0d %0d %0d %0d\n",lane,pr_depth[lane]+1,pr_consumed_row[lane],
                    pr_result[lane],pr_clipped[lane]);
            pr_rows[lane]++;
            if (pr_rows[lane]==nrows) begin
                if (pr_issues[lane]!=32*nrows || pr_steps[lane]!=32*nrows)
                    $fatal(1,"Projection %0d did not consume exactly one issue per term",lane);
                pr_depth[lane]++;
                $fwrite(pr_profile,"%0d %0d %0d %0d %0d %0d %0d %0d\n",lane,pr_depth[lane],pr_reads[lane],
                        pr_mac[lane],pr_round[lane],pr_holds[lane],pr_issues[lane],pr_rows[lane]);
                pr_reads[lane]=0;
                pr_mac[lane]=0;
                pr_round[lane]=0;
                pr_holds[lane]=0;
                pr_issues[lane]=0;
                pr_steps[lane]=0;
                pr_rows[lane]=0;
            end
        end
    end
    if (int'(dut.core_phase)==14) begin
        pr_ff_wait++;
        if (dut.core.ff.state==dut.core.ff.PAIR && !(dut.core.ff.g_valid && dut.core.ff.u_valid)) begin
            if (dut.core.ff.index==0) pr_first_pair_wait++;
            else pr_later_pair_wait++;
        end
        if (dut.core.ff.result_valid && dut.core.ff.result_ready && dut.core.ff.result_row==9'd31) begin
            pr_ff_depth++;
            $fwrite(pr_pairs,"%0d %0d %0d %0d\n",pr_ff_depth,pr_ff_wait,pr_first_pair_wait,pr_later_pair_wait);
            pr_ff_wait=0;
            pr_first_pair_wait=0;
            pr_later_pair_wait=0;
        end
    end
end

final begin
    for (int lane=0; lane<4; lane++) begin
        if (pr_steps[lane] || pr_issues[lane] || pr_rows[lane])
            $fatal(1,"Projection trace ended mid-request");
    end
    if (pr_ff_wait) $fatal(1,"Feed-forward trace ended mid-request");
    $fclose(pr_profile);
    $fclose(pr_outputs);
    $fclose(pr_pairs);
end
