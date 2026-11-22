    logic [48:0] m_axi_araddr;
    logic [5:0] m_axi_arid, m_axi_rid;
    logic [7:0] m_axi_arlen;
    logic [2:0] m_axi_arsize, m_axi_arprot;
    logic [1:0] m_axi_arburst, m_axi_rresp;
    logic m_axi_arlock, m_axi_arvalid, m_axi_arready, m_axi_rvalid, m_axi_rready;
    logic [3:0] m_axi_arcache, m_axi_arqos;
    logic [63:0] m_axi_rdata;
    logic m_axi_rlast;
    localparam logic [31:0] DDR_BASE = 32'h7fffb000;
    logic [63:0] matrix [0:2559];
    integer ar_waited,r_delay,burst_index,beat_address,beats_left,commands,beats,matched_beats;
    integer invocation_reads, invocation_beats, invocation_extra, invocation_count;
    integer ar_stalls_local,response_waits_local,projection_clocks,projection_file,operand_clocks;
    integer injected_fault, perturb;
    logic hold_ar,hold_r,inject_wrong_id,inject_bad_resp,inject_early_last,inject_late_last;
    logic saw_held_ar,returning;
    logic [48:0] held_araddr;
    string matrix_path;
    assign m_axi_arready = !hold_ar && !returning && ar_waited >= (commands % 2)*2;
    assign m_axi_rvalid = !hold_r && returning && r_delay == 0;
    assign m_axi_rid = inject_wrong_id ? 6'd1 : 6'd0;
    assign m_axi_rresp = inject_bad_resp ? 2'd2 : 2'd0;
    assign m_axi_rlast = !inject_late_last && (beats_left == 1 || inject_early_last || inject_wrong_id);
    assign m_axi_rdata = matrix[beat_address];

    initial begin
        if (!$value$plusargs("MATRIX=%s",matrix_path)) $fatal(1,"Missing DDR matrix");
        $readmemh(matrix_path,matrix);
        projection_file = $fopen("ddr-profile.txt","w");
        if (projection_file == 0) $fatal(1,"Cannot capture logits DDR counters");
    end

    always @(posedge aclk) if (aresetn) begin
        if (saw_held_ar && (!m_axi_arvalid || m_axi_araddr != held_araddr || m_axi_arlen != 8'd7))
            $fatal(1,"Master changed stalled AXI burst");
        saw_held_ar <= m_axi_arvalid && !m_axi_arready;
        held_araddr <= m_axi_araddr;
        if (m_axi_arvalid && !m_axi_arready) ar_waited <= ar_waited+1;
        if (m_axi_arvalid && m_axi_arready) begin
            if (returning || m_axi_araddr != {17'd0,DDR_BASE}+49'(burst_index*64) ||
                m_axi_araddr[5:0] != 0 || m_axi_araddr[11:0] > 12'hfc0 ||
                m_axi_arlen != 7 || m_axi_arid != 0 || m_axi_arsize != 3 || m_axi_arburst != 1 || m_axi_arprot != 2 ||
                (dut.ddr_mode && (!dut.ddr_request || dut.ddr_group != 6'(burst_index/8))))
                $fatal(1,"Wrong logits burst %0d address=%h count=%d",burst_index,m_axi_araddr,m_axi_arlen);
            commands <= commands+1;
            burst_index <= (burst_index+1)%320;
            ar_waited <= 0;
            returning <= 1;
            beat_address <= burst_index*8;
            beats_left <= 8;
            r_delay <= matched_beats%4;
        end
        if (returning && r_delay > 0) r_delay <= r_delay-1;
        if (m_axi_rvalid && m_axi_rready) begin
            beats <= beats+1;
            if (inject_wrong_id) begin
                inject_wrong_id <= 0;
                hold_r <= 1;
            end else if (inject_early_last) begin
                inject_early_last <= 0;
                hold_r <= 1;
            end else if (inject_late_last && beats_left == 1) begin
                inject_late_last <= 0;
                hold_r <= 1;
            end
            if (!inject_wrong_id) begin
                matched_beats <= matched_beats+1;
                if (beats_left == 1 && !inject_late_last) returning <= 0;
                else if (beats_left > 1) begin
                    beat_address <= beat_address+1;
                    beats_left <= beats_left-1;
                    r_delay <= (matched_beats+1)%4;
                end
            end
        end
        if (dut.ddr_mac) begin
            int group_index, coord, address;
            logic [127:0] expected_pair;
            group_index = int'(dut.core.logits.group_index);
            coord = int'(dut.core.logits.coordinate);
            address = (group_index*32+coord)*2;
            expected_pair = {matrix[address+1],matrix[address]};
            // Check the actual operands entering the shared signed MAC lanes.
            if (dut.ddr_weights !== expected_pair)
                $fatal(1,"Wrong coefficient vector at group %0d coordinate %0d",group_index,coord);
            for (int lane=0;lane<8;lane++) begin
                logic [15:0] row_word;
                row_word = words[(group_index*8+lane)*32+coord][15:0];
                if (perturb && group_index*8+lane == 256) row_word = 0;
                if (expected_pair[lane*16+:16] !== row_word)
                    $fatal(1,"Packed order not identical to the frozen tied weights");
            end
        end
        if (dut.core_phase == 2 && dut.core.current_token == 256 &&
            dut.core.embed_value !== words[8192+int'(dut.core.coordinate)][15:0])
            $fatal(1,"External logits weights changed a local embedding coordinate");
        if (observing && dut.projection_start) begin
            invocation_reads = 0;
            invocation_beats = 0;
            invocation_extra = 0;
            ar_stalls_local = 0;
            response_waits_local = 0;
            projection_clocks = 0;
            operand_clocks = 0;
        end
        if (observing) begin
            invocation_reads += int'(m_axi_arvalid && m_axi_arready);
            invocation_beats += int'(m_axi_rvalid && m_axi_rready);
            invocation_extra += int'(dut.ddr_extra_clock);
            ar_stalls_local += int'(m_axi_arvalid && !m_axi_arready);
            response_waits_local += int'(m_axi_rready && !m_axi_rvalid);
            projection_clocks += int'(dut.projection_busy);
            operand_clocks += int'(dut.ddr_mac);
            if (dut.core_logit_valid && dut.selected_ready && dut.core_logit_index == 319) begin
                if (operand_clocks != 1280) $fatal(1,"Wrong number of eight-lane logits operands");
                invocation_count++;
                $fwrite(projection_file,"%0d %0d %0d %0d %0d %0d %0d\n",invocation_count,
                        invocation_reads,invocation_beats,invocation_extra,ar_stalls_local,response_waits_local,
                        projection_clocks);
            end
        end
    end
    final $fclose(projection_file);
