`timescale 1ns/1ps
module dense_burst_tb;
    logic clk = 0;
    always #5 clk = !clk;
    logic reset = 1;
    logic external_mode, external_request, external_valid, external_fault;
    logic external_extra_clock, invocation_start;
    logic [9:0] external_index;
    logic signed [15:0] external_weight;
    logic input_valid, input_ready, weight_valid, weight_ready, start, start_ready, busy;
    logic [7:0] input_address, weight_address;
    logic [8:0] weight_row;
    logic signed [15:0] input_value, weight_value;
    logic result_valid, result_ready, saturated, step_valid;
    logic signed [15:0] result, step_input, step_weight;
    logic [8:0] result_row, step_row;
    logic [7:0] step_index;
    logic signed [31:0] step_product;
    logic signed [47:0] step_sum;

    logic [48:0] araddr;
    logic arvalid, arready, rvalid, rready, reader_busy;
    logic [63:0] rdata;
    logic ar_accept, r_accept, ar_blocked, r_wait, fault_event;
    localparam logic [31:0] BASE = 32'h7ffff800;
    logic [63:0] beats[0:255];
    logic signed [15:0] expected_inputs[0:31], expected_weights[0:1023], bram_weights[0:1023];
    logic signed [31:0] expected_products[0:1023];
    logic signed [47:0] expected_sums[0:1023];
    logic [16:0] expected_rows[0:31];
    integer addresses_seen, returns_seen, rows_seen, steps_seen, ar_stall, response_delay;
    integer extras_seen, ar_stalls_seen, waits_seen;
    logic have_response;
    integer mode, reads_per_projection, beats_per_projection, extra_per_projection;
    integer beat_offset, returns_left;
    logic [7:0] arlen;
    string path;

    dense_ddr_projection #(.INPUTS(32),.OUTPUTS(32),.SHIFT(16),.RESULT_BITS(16)) projection (.*);
    projection_ddr_reader reader (
        .clk(clk),.reset(reset),.cancel(1'b0),.clear(1'b0),.request(external_request),.index(external_index),
        .base(BASE),.mode(2'(mode)),.valid(external_valid),.fault(external_fault),.busy(reader_busy),.weight(external_weight),
        .araddr(araddr),.arlen(arlen),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rid(6'd0),.rresp(2'b00),
        .rlast(returns_left==1),.rvalid(rvalid),.rready(rready),.ar_accept(ar_accept),.r_accept(r_accept),
        .ar_blocked(ar_blocked),.r_wait(r_wait),.fault_event(fault_event)
    );

    assign arready = !have_response && ar_stall >= (addresses_seen % 2)*2;
    assign rvalid = have_response && response_delay == 0;
    always @(posedge clk) if (!reset) begin
        if (external_fault || fault_event) $fatal(1,"Unexpected reader fault");
        if (ar_blocked) begin
            ar_stall <= ar_stall+1;
            ar_stalls_seen <= ar_stalls_seen+1;
        end
        if (r_wait) waits_seen <= waits_seen+1;
        if (external_extra_clock) extras_seen <= extras_seen+1;
        if (ar_accept) begin
            int weight_index, expected_len;
            weight_index = mode==1 ? addresses_seen : mode==2 ? addresses_seen*4 : addresses_seen*32;
            expected_len = mode==3 ? 7 : 0;
            if (!external_mode || have_response || external_index != 10'(weight_index) ||
                arlen != 8'(expected_len) || araddr != {17'd0,BASE} + 49'((weight_index/4)*8))
                $fatal(1,"Invalid beat address at coefficient %0d",weight_index);
            ar_stall <= 0;
            response_delay <= returns_seen % 4;
            beat_offset <= weight_index/4;
            rdata <= beats[weight_index/4];
            returns_left <= expected_len+1;
            addresses_seen <= addresses_seen+1;
            have_response <= 1;
        end
        if (have_response && response_delay > 0) response_delay <= response_delay-1;
        if (r_accept) begin
            returns_seen <= returns_seen+1;
            if (returns_left == 1) have_response <= 0;
            else begin
                returns_left <= returns_left-1;
                response_delay <= (returns_seen+1)%4;
                rdata <= beats[beat_offset+1];
                beat_offset <= beat_offset+1;
            end
        end
        if (external_request && external_valid && external_weight !== expected_weights[external_index])
            $fatal(1,"Wrong weight lane at operand %0d",external_index);
        if (step_valid) begin
            if (steps_seen >= 1024 || step_row != 9'(steps_seen/32) || step_index != 8'(steps_seen%32) ||
                step_input !== expected_inputs[steps_seen%32] || step_weight !== expected_weights[steps_seen] ||
                step_product !== expected_products[steps_seen] || step_sum !== expected_sums[steps_seen])
                $fatal(1,"Wrong signed multiply or sum at coefficient %0d",steps_seen);
            steps_seen <= steps_seen+1;
        end
        if (result_valid && result_ready) begin
            if (rows_seen >= 32 || result_row != 9'(rows_seen) || {saturated,result} !== expected_rows[rows_seen])
                $fatal(1,"Wrong rounded result or saturation at row %0d",rows_seen);
            rows_seen <= rows_seen+1;
        end
    end

    initial begin
        if (!$value$plusargs("FIXTURE=%s",path) || !$value$plusargs("MODE=%d",mode))
            $fatal(1,"Missing dense fixtures");
        $readmemh({path,"/x.hex"},expected_inputs);
        $readmemh({path,"/bram.hex"},bram_weights);
        $readmemh({path,"/w.hex"},expected_weights);
        $readmemh({path,"/p.hex"},expected_products);
        $readmemh({path,"/sum.hex"},expected_sums);
        $readmemh({path,"/y.hex"},expected_rows);
        $readmemh({path,"/ddr.hex"},beats);
        repeat(2) @(negedge clk);
        reset = 0;
        external_mode = mode != 0;
        case (mode)
            0: begin reads_per_projection=0; beats_per_projection=0; extra_per_projection=0; end
            1: begin reads_per_projection=1024; beats_per_projection=1024; extra_per_projection=4608; end
            2: begin reads_per_projection=256; beats_per_projection=256; extra_per_projection=1152; end
            3: begin reads_per_projection=32; beats_per_projection=256; extra_per_projection=704; end
            default: $fatal(1,"Unexpected dense mode");
        endcase
        result_ready = 1;
        for (int index = 0; index < 1024; index++) begin
            weight_valid = 1;
            weight_address = 8'(index%32);
            weight_row = 9'(index/32);
            weight_value = bram_weights[index];
            input_valid = index < 32;
            input_address = 8'(index%32);
            input_value = expected_inputs[index%32];
            @(negedge clk);
        end
        weight_valid = 0;
        input_valid = 0;
        start = 1;
        @(negedge clk);
        start = 0;
        wait(rows_seen == 32);
        @(negedge clk);
        if (steps_seen != 1024 || addresses_seen != reads_per_projection ||
            returns_seen != beats_per_projection || extras_seen != extra_per_projection ||
            ar_stalls_seen != reads_per_projection || waits_seen != 3*beats_per_projection/2)
            $fatal(1,"Dense count mismatch");
        $display("PASS dense mode=%0d products=%0d rows=%0d addresses=%0d AXI_beats=%0d extra=%0d",mode,steps_seen,
            rows_seen,addresses_seen,returns_seen,extras_seen);
        $finish;
    end
    initial begin #1000000; $fatal(1,"Dense AXI watchdog"); end
endmodule
