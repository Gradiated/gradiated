`timescale 1ns/1ps
module logits_arithmetic_tb;
    logic clk=0, reset=1;
    always #5 clk=!clk;
    logic fetch_valid,fetch_fault,fetch_request,operand_read,mac_active,fetch_wait,invocation_start;
    logic [127:0] fetched_weights;
    logic [5:0] fetch_group;
    logic [4:0] fetch_coordinate;
    logic input_valid,input_ready,start,start_ready,busy,result_valid,result_ready,saturated;
    logic [7:0] input_address;
    logic signed [15:0] input_value,result;
    logic [8:0] result_row;
    logic transport_busy,arvalid,arready,rvalid,rready,ar_accept,r_accept,ar_blocked,r_wait,fault_event;
    logic [48:0] araddr;
    logic [63:0] rdata;
    localparam logic [31:0] BASE=32'h7fffb000;
    logic [63:0] staging [0:2559];
    logic [15:0] inputs [0:31];
    logic [16:0] results [0:319];
    logic [47:0] sums [0:10239];
    integer invocation,consumed,cycles,addresses,beats,rows,stalls,waiting,beat_left,location,held;
    integer expected_partial,expected_row;
    logic stalled_score;
    logic [25:0] held_score;
    logic early_group_ready, stop_at_prefetched_group, late_group_ready;
    string location_path;

    logits_parallel_ddr #(.RESULT_BITS(16)) dut (.*);
    logits_group_reader reader (
        .clk(clk),.reset(reset),.cancel(1'b0),.clear(1'b0),.request(fetch_request),
        .group_index(fetch_group),.base(BASE),.read_pair(operand_read),.read_coordinate(fetch_coordinate),
        .weights(fetched_weights),.valid(fetch_valid),.fault(fetch_fault),.busy(transport_busy),
        .araddr(araddr),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rid(6'd0),.rresp(2'd0),
        .rlast(beat_left==1),.rvalid(rvalid),.rready(rready),.ar_accept(ar_accept),.r_accept(r_accept),
        .ar_blocked(ar_blocked),.r_wait(r_wait),.fault_event(fault_event));
    assign arready = beat_left==0 && stalls >= (addresses%2)*2;
    assign rvalid = beat_left!=0 && waiting==0;
    // The next invocation's same bus addresses return distinct group data.
    assign rdata = staging[(location+64*invocation)%2560];
    assign result_ready = !(invocation==0 && rows==0 && held<180) && cycles%5!=3;
    assign expected_partial = (consumed*8+256*invocation)%10240;
    assign expected_row = (rows+8*invocation)%320;

    for (genvar lane=0;lane<8;lane++) begin : partial
        always @(posedge clk) if (!reset && mac_active)
            if (dut.bank[lane].next_sum !== sums[expected_partial+lane])
                $fatal(1,"Lane %d incorrect signed accumulation at coordinate count %d",lane,consumed);
    end

    always @(posedge clk) if (!reset) begin
        cycles<=cycles+1;
        if (fetch_fault || fault_event) $fatal(1,"Unexpected AXI arithmetic fixture fault");
        if (ar_blocked) stalls<=stalls+1;
        if (ar_accept) begin
            if (!busy || beat_left!=0 || araddr!={17'd0,BASE}+49'(64*(addresses%320)) ||
                reader.next_fetch_group!=6'((addresses%320)/8) ||
                reader.next_fetch_group<fetch_group || reader.next_fetch_group>fetch_group+6'd1 ||
                addresses>=320*(invocation+1))
                $fatal(1,"Read outside the current invocation or the next group");
            location<=addresses%320*8;
            beat_left<=8;
            waiting<=beats%4;
            addresses<=addresses+1;
            stalls<=0;
        end
        if (beat_left!=0 && waiting>0) waiting<=waiting-1;
        if (r_accept) begin
            location<=location+1;
            beats<=beats+1;
            waiting<=(beats+1)%4;
            beat_left<=beat_left-1;
        end
        if (operand_read && r_accept && reader.read_address==reader.write_coordinate)
            $fatal(1,"Same buffer coordinate read and write");
        if (mac_active) begin
            if (beats<2560*invocation+64*(int'(fetch_group)+1))
                $fatal(1,"Consumed a partially filled or stale group");
            consumed<=consumed+1;
        end
        if (result_valid && !result_ready && rows==0) held<=held+1;
        if (stalled_score && (!result_valid || held_score!={result_row,saturated,result}))
            $fatal(1,"Held result changed under backpressure");
        stalled_score<=result_valid && !result_ready;
        if (result_valid && !result_ready) held_score<={result_row,saturated,result};
        if (result_valid && !result_ready && invocation==0 && rows==0 &&
            reader.next_fetch_group==2 && !transport_busy && !arvalid)
            stop_at_prefetched_group<=1;
        if (operand_read && !mac_active && invocation==0 && fetch_group==1 &&
            reader.next_fetch_group==2 && !reader.complete_group)
            early_group_ready<=1;
        if (operand_read && !mac_active && invocation==0 && fetch_group==2 && reader.complete_group)
            late_group_ready<=1;
        if (result_valid && result_ready) begin
            if (result_row!=9'(rows%320) || {saturated,result}!==results[expected_row])
                $fatal(1,"Signed rounding/clipping mismatch at output row %d",rows);
            rows<=rows+1;
        end
    end

    task automatic launch_scores;
        if (!start_ready) $fatal(1,"Score unit did not return idle");
        start=1;
        @(negedge clk);
        start=0;
    endtask

    initial begin
        if (!$value$plusargs("FIXTURE=%s",location_path)) $fatal(1,"Missing directed arithmetic fixtures");
        $readmemh({location_path,"/x.hex"},inputs);
        $readmemh({location_path,"/sums.hex"},sums);
        $readmemh({location_path,"/results.hex"},results);
        $readmemh({location_path,"/weights.hex"},staging);
        repeat(2) @(negedge clk);
        reset=0;
        for (integer i=0;i<32;i++) begin
            input_valid=1; input_address=8'(i); input_value=inputs[i];
            @(negedge clk);
        end
        input_valid=0;
        #1;
        launch_scores();
        wait(rows==320);
        repeat(16) @(negedge clk);
        if (addresses!=320 || beats!=2560 || busy || transport_busy || arvalid || !early_group_ready ||
            !late_group_ready || !stop_at_prefetched_group)
            $fatal(1,"Missing slot rotation/overlap or unexpected transfer between invocations");
        invocation=1;
        launch_scores();
        wait(rows==640);
        repeat(16) @(negedge clk);
        if (addresses!=640 || beats!=5120 || consumed!=2560 || busy || transport_busy || arvalid)
            $fatal(1,"Incomplete directed score projections");
        $display("PASS directed logits arithmetic, 640 ordered rows, 20480 partial sums, early and late fill, backpressure and fresh next invocation");
        $finish;
    end
    initial begin #1000000;$fatal(1,"Directed logits deadline");end
endmodule
