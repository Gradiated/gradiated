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
    integer consumed_coordinates,ready_cycles,address_count,beat_count,rows,stalls,waiting,beat_left,location;
    string location_path;

    logits_parallel_ddr #(.RESULT_BITS(16)) dut (.*);
    logits_group_reader reader (
        .clk(clk),.reset(reset),.cancel(1'b0),.clear(1'b0),.request(fetch_request),
        .group_index(fetch_group),.base(BASE),.read_pair(operand_read),.read_coordinate(fetch_coordinate),
        .weights(fetched_weights),.valid(fetch_valid),.fault(fetch_fault),.busy(transport_busy),
        .araddr(araddr),.arvalid(arvalid),.arready(arready),.rdata(rdata),.rid(6'd0),.rresp(2'd0),
        .rlast(beat_left==1),.rvalid(rvalid),.rready(rready),.ar_accept(ar_accept),.r_accept(r_accept),
        .ar_blocked(ar_blocked),.r_wait(r_wait),.fault_event(fault_event));
    assign arready = beat_left==0 && stalls >= (address_count%2)*2;
    assign rvalid = beat_left!=0 && waiting==0;
    assign rdata = staging[location];
    assign result_ready = ready_cycles%5!=3;

    for (genvar lane=0;lane<8;lane++) begin : partial
        always @(posedge clk) if (!reset && mac_active)
            if (dut.bank[lane].next_sum !== sums[consumed_coordinates*8+lane])
                $fatal(1,"Lane %d incorrect signed accumulation at coordinate count %d",lane,consumed_coordinates);
    end
    always @(posedge clk) if (!reset) begin
        ready_cycles <= ready_cycles+1;
        if (fetch_fault || fault_event) $fatal(1,"Unexpected AXI arithmetic fixture fault");
        if (ar_blocked) stalls<=stalls+1;
        if (ar_accept) begin
            if (beat_left != 0 || araddr != {17'd0,BASE}+49'(64*address_count) ||
                fetch_group != 6'(address_count/8) || address_count >= 320)
                $fatal(1,"Unexpected address or prefetch for the next group");
            location <= address_count*8;
            beat_left <= 8;
            waiting <= beat_count%4;
            address_count<=address_count+1;
            stalls<=0;
        end
        if (beat_left!=0 && waiting>0) waiting<=waiting-1;
        if (r_accept) begin
            location<=location+1;
            beat_count<=beat_count+1;
            waiting<=(beat_count+1)%4;
            beat_left<=beat_left-1;
        end
        if (mac_active) consumed_coordinates<=consumed_coordinates+1;
        if (result_valid && result_ready) begin
            if (result_row != 9'(rows) || {saturated,result} !== results[rows])
                $fatal(1,"Signed rounding/clipping mismatch at output row %d",rows);
            rows<=rows+1;
        end
    end
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
        start=1;
        @(negedge clk);
        start=0;
        wait(rows==320);
        @(negedge clk);
        if (address_count!=320 || beat_count!=2560 || consumed_coordinates!=1280)
            $fatal(1,"Incomplete directed score projection");
        $display("PASS directed logits arithmetic, 320 ordered rows, 10240 partial sums");
        $finish;
    end
    initial begin #1000000;$fatal(1,"Directed logits deadline");end
endmodule
