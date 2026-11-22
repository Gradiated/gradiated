`timescale 1ns/1ps
module shared_scalar_tb;
    logic clk = 0, reset = 1;
    always #5 clk = ~clk;

    logic [2:0] cmd_valid, cmd_ready, result_valid, result_ready, status_error;
    logic signed [2:0][63:0] a, b, scalar_result;
    logic signed [2:0][7:0] exponent;
    logic [2:0] request, grant, owner_valid, local_ready, allow_result;
    logic [2:0][63:0] abs_a, abs_b;
    logic [127:0] product;
    int grant_log[3];
    int grant_count = 0;

    rmsnorm_shared_mul shared (
        .clk(clk),.reset(reset),.request(request),.grant(grant),
        .operand_a(abs_a),.operand_b(abs_b),.result_valid(owner_valid),
        .result_ready(local_ready & allow_result),.result(product)
    );

    for (genvar lane=0; lane<3; lane++) begin : client
        fixed_scalar_norm_dsp scalar (
            .clk(clk),.reset(reset),.cmd_valid(cmd_valid[lane]),.cmd_ready(cmd_ready[lane]),
            .cmd_op(3'd2),.cmd_a(a[lane]),.cmd_b(b[lane]),.cmd_shift(8'sd0),
            .table_valid(1'b0),.table_ready(),.table_kind(1'b0),
            .table_index(9'd0),.table_value(32'd0),
            .result_valid(result_valid[lane]),.result_ready(result_ready[lane]),
            .result(scalar_result[lane]),.result_exponent(exponent[lane]),.error(status_error[lane]),
            .mul_request(request[lane]),.mul_grant(grant[lane]),.mul_a(abs_a[lane]),.mul_b(abs_b[lane]),
            .mul_valid(owner_valid[lane] & allow_result[lane]),.mul_ready(local_ready[lane]),.mul_value(product)
        );
    end

    always @(posedge clk) if (!reset && |grant) begin
        assert ($onehot(grant) && (grant & request) == grant)
            else $fatal(1,"Grant chose an invalid requester");
        if (grant_count < 3)
            grant_log[grant_count] = grant[0] ? 0 : grant[1] ? 1 : 2;
        grant_count++;
    end

    task automatic wait_outputs(input logic [2:0] expected);
        int clocks;
        for (clocks=0; clocks<100 && result_valid != expected; clocks++)
            @(negedge clk);
        assert (result_valid == expected) else $fatal(1, "Missing expected clients' output");
    endtask

    task automatic reset_all;
        reset = 1;
        cmd_valid = 0;
        result_ready = 0;
        allow_result = '1;
        #1;
        assert (!grant && !owner_valid) else $fatal(1,"Reset failed to mask shared handshake");
        @(negedge clk);
        reset = 0;
        #1;
        assert (cmd_ready == '1 && !result_valid && !owner_valid && !request && shared.owner == 0)
            else $fatal(1,"Reset retained a stale request or result");
        @(negedge clk);
    endtask

    task automatic check_small_product(input int lane, input logic signed [63:0] lhs, rhs, expected);
        a[lane] = lhs;
        b[lane] = rhs;
        cmd_valid = 3'b001 << lane;
        @(negedge clk);
        cmd_valid = 0;
        wait_outputs(3'b001 << lane);
        assert (scalar_result[lane] == expected && !status_error[lane])
            else $fatal(1,"Fresh command after reset got stale data");
        result_ready = 3'b001 << lane;
        @(negedge clk);
        result_ready = 0;
    endtask

    initial begin
        int handle, batches, denied_count;
        string path;
        logic signed [2:0][63:0] expected;
        logic [2:0] expected_error;
        logic [127:0] held_product;
        cmd_valid=0;
        result_ready=0;
        allow_result='1;
        a=0;
        b=0;
        if (!$value$plusargs("TEST_VECTORS=%s",path) || !$value$plusargs("TEST_BATCHES=%d",batches))
            $fatal(1,"Missing arithmetic fixture");
        handle=$fopen(path,"r");
        if (!handle) $fatal(1,"Cannot read arithmetic fixture");
        @(negedge clk);
        reset_all();

        // Three real clients request together. Results are checked after all
        // have arrived, while early scalar outputs remain backpressured.
        for (int batch=0; batch<batches; batch++) begin
            for (int i=0; i<3; i++) begin
                logic signed [63:0] lhs, rhs, value;
                logic fault;
                if ($fscanf(handle,"%h %h %h %h",lhs,rhs,value,fault)!=4)
                    $fatal(1,"Missing arithmetic vector");
                a[i] = lhs;
                b[i] = rhs;
                expected[i] = value;
                expected_error[i] = fault;
            end
            grant_count=0;
            cmd_valid='1;
            @(negedge clk);
            cmd_valid=0;
            wait_outputs('1);
            assert (grant_count==3 && grant_log[0]==0 && grant_log[1]==1 && grant_log[2]==2)
                else $fatal(1,"Simultaneous requests were lost or misordered");
            repeat (3) begin
                assert (result_valid=='1 && scalar_result==expected && status_error==expected_error &&
                        exponent=='0 && cmd_ready==0)
                    else $fatal(1,"Incorrect or unstable scalar response batch %0d",batch);
                @(negedge clk);
            end
            result_ready='1;
            @(negedge clk);
            result_ready=0;
            assert (cmd_ready=='1 && !result_valid) else $fatal(1,"Scalar output failed to retire");
        end
        $fclose(handle);

        // Keep a shared response blocked even as a second client waits.
        allow_result=3'b110;
        a[0]=2;
        b[0]=-5;
        a[1]=7;
        b[1]=11;
        cmd_valid=3'b011;
        @(negedge clk);
        cmd_valid=0;
        for (int clocks=0; owner_valid==0 && clocks<20; clocks++) @(negedge clk);
        assert (owner_valid==3'b001) else $fatal(1,"Wrong blocked owner");
        held_product=product;
        assert (held_product==10) else $fatal(1,"Wrong blocked product");
        denied_count=0;
        repeat (4) begin
            assert (owner_valid==3'b001 && product==held_product && request==3'b010 && grant==0 &&
                    result_valid==0)
                else $fatal(1,"Blocked shared result was overwritten or went to another client");
            denied_count++;
            @(negedge clk);
        end
        allow_result='1;
        wait_outputs(3'b011);
        assert (scalar_result[0]==(-64'sd10) && scalar_result[1]==64'd77 && status_error[1:0]==0)
            else $fatal(1,"Blocked handoff corrupted data");
        result_ready='1;
        @(negedge clk);
        result_ready=0;

        // Abort before grant and after each of its four pipeline edges.
        for (int elapsed=0; elapsed<=4; elapsed++) begin
            a[2]=789;
            b[2]=-123;
            allow_result=3'b011;
            cmd_valid=3'b100;
            @(negedge clk);
            cmd_valid=0;
            repeat (elapsed) @(negedge clk);
            assert (int'(shared.state)==elapsed) else $fatal(1,"Reset missed stage %0d",elapsed);
            reset_all();
            check_small_product((elapsed+1)%3, -33, 17, -561);
        end
        $display("PASS shared scalar: %0d exact signed products, %0d blocked response clocks, five reset points",
                 batches*3,denied_count);
        $finish;
    end
endmodule
