    logic fetch_launch, fetch_work, capture_coordinate_zero, accepted_transfer, other_score_work;
    integer overlap_file, work_cycles, mac_overlap, other_overlap, captures, work_captures;
    integer mac_transfers, other_transfers;
    assign fetch_launch = dut.ddr_request && !dut.ddr_busy;
    assign fetch_work = fetch_launch || dut.ddr_busy;
    assign capture_coordinate_zero = dut.ddr_operand_read && !dut.ddr_mac;
    assign accepted_transfer = dut.ddr_ar_accept || dut.ddr_r_accept;
    assign other_score_work = dut.projection_busy && !dut.ddr_mac &&
                              !dut.ddr_extra_clock && !capture_coordinate_zero;

    initial begin
        overlap_file = $fopen("overlap.txt","w");
        if (overlap_file == 0) $fatal(1,"Cannot capture direct clock overlap");
    end
    final $fclose(overlap_file);

    always @(posedge aclk) if (aresetn && observing) begin
        if (dut.projection_start) begin
            work_cycles = 0;
            mac_overlap = 0;
            other_overlap = 0;
            captures = 0;
            work_captures = 0;
            mac_transfers = 0;
            other_transfers = 0;
        end
        if (fetch_work && !dut.projection_busy)
            $fatal(1,"DDR read outside the current score invocation");
        work_cycles += int'(fetch_work);
        mac_overlap += int'(fetch_work && dut.ddr_mac);
        other_overlap += int'(fetch_work && other_score_work);
        mac_transfers += int'(accepted_transfer && dut.ddr_mac);
        other_transfers += int'(accepted_transfer && other_score_work);
        captures += int'(capture_coordinate_zero);
        work_captures += int'(fetch_work && capture_coordinate_zero);
        if (dut.core_logit_valid && dut.selected_ready && dut.core_logit_index == 319)
            $fwrite(overlap_file,"%0d %0d %0d %0d %0d %0d %0d %0d\n",logit_starts,
                    work_cycles,mac_overlap,other_overlap,captures,work_captures,mac_transfers,other_transfers);
    end
