    logic [48:0] m_axi_araddr;
    logic [5:0] m_axi_arid, m_axi_rid = 0;
    logic [7:0] m_axi_arlen;
    logic [2:0] m_axi_arsize, m_axi_arprot;
    logic [1:0] m_axi_arburst, m_axi_rresp = 0;
    logic m_axi_arlock, m_axi_arvalid, m_axi_arready, m_axi_rvalid, m_axi_rready;
    logic [3:0] m_axi_arcache, m_axi_arqos;
    logic [63:0] m_axi_rdata;
    logic m_axi_rlast = 1;
    localparam logic [31:0] DDR_BASE = 32'h7ffff800;
    logic [63:0] ddr_matrix [0:255];
    integer ddr_arm, ar_waited = 0, r_delay = 0, beat_index = 0, ddr_profile;
    integer invocation_reads, invocation_beats, invocation_extra, invocation_count;
    integer ar_stalls_local, response_waits_local, projected_clocks, measured_clocks;
    logic returning = 0;
    string matrix_path;
    assign m_axi_arready = !hold_ar && !returning && ar_waited >= ((beat_index % 2) * 2);
    assign m_axi_rvalid = !hold_r && returning && r_delay == 0 && (m_axi_rlast || response_count == 0);

    initial begin
        if (!$value$plusargs("DDR=%d",ddr_arm) || !$value$plusargs("MATRIX=%s",matrix_path))
            $fatal(1,"Missing DDR simulation parameters");
        $readmemh(matrix_path,ddr_matrix);
        ddr_profile = $fopen("ddr-profile.txt","w");
        if (!ddr_profile) $fatal(1,"Cannot create DDR profile");
    end
    always @(posedge aclk) if (aresetn) begin
        if (m_axi_arvalid && !m_axi_arready) ar_waited <= ar_waited + 1;
        if (m_axi_arvalid && m_axi_arready) begin
            if (!ddr_arm || returning || m_axi_araddr != {17'd0,DDR_BASE} + 49'((beat_index/4)*8) ||
                m_axi_arid != 0 || m_axi_arlen != 0 || m_axi_arsize != 3 || m_axi_arburst != 1 || m_axi_arprot != 2)
                $fatal(1,"Invalid DDR read command %h for coefficient %d",m_axi_araddr,beat_index);
            ar_waited <= 0;
            r_delay <= beat_index % 4;
            m_axi_rdata <= ddr_matrix[beat_index/4];
            returning <= 1;
            beat_index <= (beat_index + 1) % 1024;
        end
        if (returning && r_delay > 0) r_delay <= r_delay - 1;
        if (m_axi_rvalid && m_axi_rready) begin
            if (m_axi_rlast) returning <= 0;
            else r_delay <= 0;
        end

        if (observing && dut.projection_start) begin
            invocation_reads = 0;
            invocation_beats = 0;
            invocation_extra = 0;
            ar_stalls_local = 0;
            response_waits_local = 0;
            projected_clocks = 0;
        end
        if (observing) begin
            invocation_reads += int'(m_axi_arvalid && m_axi_arready);
            invocation_beats += int'(m_axi_rvalid && m_axi_rready);
            invocation_extra += int'(dut.ddr_extra_clock);
            ar_stalls_local += int'(m_axi_arvalid && !m_axi_arready);
            response_waits_local += int'(m_axi_rready && !m_axi_rvalid);
            projected_clocks += int'(dut.projection_busy);
            if (dut.core.o_valid && dut.core.o_ready && dut.core.o_row == 31) begin
                invocation_count++;
                measured_clocks += projected_clocks;
                $fwrite(ddr_profile,"%0d %0d %0d %0d %0d %0d %0d\n",
                    invocation_count,invocation_reads,invocation_beats,invocation_extra,
                    ar_stalls_local,response_waits_local,projected_clocks);
            end
        end
    end
    final $fclose(ddr_profile);
