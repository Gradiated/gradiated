    logic [48:0] m_axi_araddr;
    logic [5:0] m_axi_arid, m_axi_rid;
    logic [7:0] m_axi_arlen;
    logic [2:0] m_axi_arsize, m_axi_arprot;
    logic [1:0] m_axi_arburst, m_axi_rresp;
    logic m_axi_arlock, m_axi_arvalid, m_axi_arready, m_axi_rvalid, m_axi_rready;
    logic [3:0] m_axi_arcache, m_axi_arqos;
    logic [63:0] m_axi_rdata;
    logic m_axi_rlast;
    localparam logic [31:0] DDR_BASE = 32'h7ffff800;
    logic [63:0] ddr_matrix [0:255];
    integer ddr_arm, ddr_profile, ar_waited, r_delay, read_within_projection;
    integer invocation_reads, invocation_beats, invocation_extra, invocation_count, operand_count;
    integer ar_stalls_local, response_waits_local, projected_clocks, measured_clocks;
    integer reads_per_projection, beats_per_projection, extra_per_projection;
    integer command_count, response_count, return_offset, returns_left, total_good_beats;
    logic hold_ar, hold_r, inject_wrong_id, inject_bad_resp, inject_early_last, inject_late_last;
    logic saw_held_ar;
    logic [48:0] held_araddr;
    logic [7:0] held_arlen;
    logic returning;
    string matrix_path;
    assign m_axi_arready = !hold_ar && !returning && ar_waited >= (command_count % 2) * 2;
    assign m_axi_rvalid = !hold_r && returning && r_delay == 0;
    assign m_axi_rid = inject_wrong_id ? 6'd1 : 6'd0;
    assign m_axi_rresp = inject_bad_resp ? 2'd2 : 2'd0;
    assign m_axi_rlast = !inject_late_last && (returns_left == 1 || inject_early_last || inject_wrong_id);
    assign m_axi_rdata = ddr_matrix[return_offset];

    initial begin
        if (!$value$plusargs("DDR=%d",ddr_arm) || !$value$plusargs("MATRIX=%s",matrix_path))
            $fatal(1,"Missing DDR simulation parameters");
        $readmemh(matrix_path,ddr_matrix);
        ddr_profile = $fopen("ddr-profile.txt","w");
        if (ddr_profile == 0) $fatal(1,"Cannot create DDR profile");
        case (ddr_arm)
            0: begin reads_per_projection=0; beats_per_projection=0; extra_per_projection=0; end
            1: begin reads_per_projection=1024; beats_per_projection=1024; extra_per_projection=4608; end
            2: begin reads_per_projection=256; beats_per_projection=256; extra_per_projection=1152; end
            3: begin reads_per_projection=32; beats_per_projection=256; extra_per_projection=704; end
            default: $fatal(1,"Unexpected DDR mode");
        endcase
    end
    always @(posedge aclk) if (aresetn) begin
        if (saw_held_ar && (!m_axi_arvalid || m_axi_araddr != held_araddr || m_axi_arlen != held_arlen))
            $fatal(1,"Stalled address changed before acceptance");
        saw_held_ar <= m_axi_arvalid && !m_axi_arready;
        held_araddr <= m_axi_araddr;
        held_arlen <= m_axi_arlen;
        if (m_axi_arvalid && !m_axi_arready) ar_waited <= ar_waited + 1;
        if (m_axi_arvalid && m_axi_arready) begin
            int first_beat, first_weight;
            case (ddr_arm)
                1: first_weight = read_within_projection;
                2: first_weight = read_within_projection*4;
                3: first_weight = read_within_projection*32;
                default: $fatal(1,"BRAM arm issued a DDR address");
            endcase
            first_beat = first_weight/4;
            if (returning || m_axi_araddr != {17'd0,DDR_BASE} + 49'(first_beat*8) ||
                m_axi_arid != 0 || m_axi_arlen != (ddr_arm == 3 ? 7 : 0) || m_axi_arsize != 3 ||
                m_axi_arburst != 1 || m_axi_arprot != 2 || dut.ddr_index != 10'(first_weight) ||
                (m_axi_arlen == 7 && (m_axi_araddr[5:0] != 0 || m_axi_araddr[11:0] > 12'hfc0)))
                $fatal(1,"Wrong address/length/timing %h/%d for operand %d",m_axi_araddr,m_axi_arlen,first_weight);
            command_count <= command_count+1;
            read_within_projection <= (read_within_projection+1)%reads_per_projection;
            ar_waited <= 0;
            r_delay <= total_good_beats%4;
            return_offset <= first_beat;
            returns_left <= int'(m_axi_arlen)+1;
            returning <= 1;
        end
        if (returning && r_delay > 0) r_delay <= r_delay-1;
        if (m_axi_rvalid && m_axi_rready) begin
            response_count <= response_count+1;
            if (inject_wrong_id) begin
                inject_wrong_id <= 0;
                hold_r <= 1;
            end else if (inject_early_last) begin
                inject_early_last <= 0;
                hold_r <= 1;
            end else if (inject_late_last && returns_left == 1) begin
                inject_late_last <= 0;
                hold_r <= 1;
            end
            if (!inject_wrong_id) begin
                total_good_beats <= total_good_beats+1;
                if (returns_left == 1 && !inject_late_last) returning <= 0;
                else if (returns_left > 1) begin
                    returns_left <= returns_left-1;
                    return_offset <= return_offset+1;
                    r_delay <= (total_good_beats+1)%4;
                end
            end
        end

        if (observing && dut.projection_start) begin
            invocation_reads = 0;
            invocation_beats = 0;
            invocation_extra = 0;
            ar_stalls_local = 0;
            response_waits_local = 0;
            projected_clocks = 0;
            operand_count = 0;
        end
        if (observing) begin
            invocation_reads += int'(m_axi_arvalid && m_axi_arready);
            invocation_beats += int'(m_axi_rvalid && m_axi_rready);
            invocation_extra += int'(dut.ddr_extra_clock);
            ar_stalls_local += int'(m_axi_arvalid && !m_axi_arready);
            response_waits_local += int'(m_axi_rready && !m_axi_rvalid);
            projected_clocks += int'(dut.projection_busy);
            if (dut.core.output_projection.step_valid) begin
                if (dut.core.output_projection.step_row != 9'(operand_count/32) ||
                    dut.core.output_projection.step_index != 8'(operand_count%32) ||
                    dut.core.output_projection.step_weight !==
                        $signed(ddr_matrix[operand_count/4][(operand_count%4)*16 +: 16]))
                    $fatal(1,"Wrong operand at coefficient %d",operand_count);
                operand_count++;
            end
            if (dut.core.o_valid && dut.core.o_ready && dut.core.o_row == 31) begin
                if (operand_count != 1024) $fatal(1,"Wrong number of projection operands");
                invocation_count++;
                measured_clocks += projected_clocks;
                $fwrite(ddr_profile,"%0d %0d %0d %0d %0d %0d %0d\n",
                    invocation_count,invocation_reads,invocation_beats,invocation_extra,
                    ar_stalls_local,response_waits_local,projected_clocks);
            end
        end
    end
    final $fclose(ddr_profile);
