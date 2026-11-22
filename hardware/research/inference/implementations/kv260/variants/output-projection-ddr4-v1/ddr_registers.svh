    logic ddr_mode, ddr_busy, ddr_fault, ddr_fault_event, ddr_idle;
    logic [31:0] ddr_base;
    logic ddr_request, ddr_valid;
    logic [9:0] ddr_index;
    logic signed [15:0] ddr_weight;
    logic ddr_ar_accept, ddr_r_accept, ddr_ar_blocked, ddr_r_wait;
    logic ddr_extra_clock, projection_start, projection_busy;
    logic [31:0] useful_bytes, accepted_reads, accepted_beats, faults;
    logic [31:0] extra_clocks, ar_stalls, response_waits, projections, projection_clocks;
    logic counter_full;

    assign ddr_idle = !auto_active && !core_busy && !ddr_busy;
    assign counter_full = (&useful_bytes) || (&accepted_reads) || (&accepted_beats) ||
        (&faults) || (&extra_clocks) || (&ar_stalls) || (&response_waits) ||
        (&projections) || (&projection_clocks);
    assign m_axi_arid = 6'd0;
    assign m_axi_arlen = 8'd0;
    assign m_axi_arsize = 3'd3;
    assign m_axi_arburst = 2'b01;
    assign m_axi_arlock = 1'b0;
    assign m_axi_arcache = 4'b0011;
    assign m_axi_arprot = 3'b010;
    assign m_axi_arqos = 4'd0;

    projection_ddr_reader #(.MAX_WAIT(DDR_MAX_WAIT)) projection_reader (
        .clk(aclk), .reset(!aresetn), .cancel(reset_pulse || soft_reset), .clear(clear_pulse),
        .request(ddr_request), .index(ddr_index), .base(ddr_base),
        .valid(ddr_valid), .fault(ddr_fault), .busy(ddr_busy), .weight(ddr_weight),
        .araddr(m_axi_araddr), .arvalid(m_axi_arvalid), .arready(m_axi_arready),
        .rdata(m_axi_rdata), .rid(m_axi_rid), .rresp(m_axi_rresp),
        .rlast(m_axi_rlast), .rvalid(m_axi_rvalid), .rready(m_axi_rready),
        .ar_accept(ddr_ar_accept), .r_accept(ddr_r_accept), .ar_blocked(ddr_ar_blocked),
        .r_wait(ddr_r_wait), .fault_event(ddr_fault_event)
    );

    function automatic logic [31:0] count_up(input logic [31:0] previous,
                                              input logic [1:0] increment);
        logic [32:0] sum;
        sum = {1'b0,previous} + {31'd0,increment};
        return sum[32] ? 32'hffffffff : sum[31:0];
    endfunction

    always_ff @(posedge aclk) begin
        if (!aresetn || reset_pulse) begin
            ddr_mode <= 0;
            ddr_base <= 0;
        end else if (write_execute && write_ok) begin
            if (write_address == 8'h60) ddr_base <= write_data;
            if (write_address == 8'h64) ddr_mode <= write_data[0];
        end
        if (!aresetn || reset_pulse || clear_pulse || auto_start) begin
            useful_bytes <= 0; accepted_reads <= 0; accepted_beats <= 0; faults <= 0;
            extra_clocks <= 0; ar_stalls <= 0; response_waits <= 0;
            projections <= 0; projection_clocks <= 0;
        end else if (!reset_pulse && !soft_reset) begin
            useful_bytes <= count_up(useful_bytes, {ddr_valid,1'b0});
            accepted_reads <= count_up(accepted_reads, {1'b0,(ddr_ar_accept && ddr_mode)});
            accepted_beats <= count_up(accepted_beats, {1'b0,(ddr_r_accept && ddr_mode)});
            faults <= count_up(faults, {1'b0,ddr_fault_event});
            extra_clocks <= count_up(extra_clocks, {1'b0,ddr_extra_clock});
            ar_stalls <= count_up(ar_stalls, {1'b0,ddr_ar_blocked});
            response_waits <= count_up(response_waits, {1'b0,ddr_r_wait});
            projections <= count_up(projections, {1'b0,projection_start});
            projection_clocks <= count_up(projection_clocks, {1'b0,projection_busy});
        end
    end
