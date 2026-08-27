`timescale 1ns/1ps

module tb_kda_axi;
    localparam integer D = 16;
    localparam integer LANES = 4;
    localparam integer EXPECTED_CYCLES = 7 * D * (D / LANES);

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg [15:0] awaddr = 16'd0;
    reg [2:0] awprot = 3'd0;
    reg awvalid = 1'b0;
    wire awready;
    reg [31:0] wdata = 32'd0;
    reg [3:0] wstrb = 4'hf;
    reg wvalid = 1'b0;
    wire wready;
    wire [1:0] bresp;
    wire bvalid;
    reg bready = 1'b1;
    reg [15:0] araddr = 16'd0;
    reg [2:0] arprot = 3'd0;
    reg arvalid = 1'b0;
    wire arready;
    wire [31:0] rdata;
    wire [1:0] rresp;
    wire rvalid;
    reg rready = 1'b1;

    reg [7:0] q_values [0:3*D-1];
    reg [7:0] k_values [0:3*D-1];
    reg [7:0] v_values [0:3*D-1];
    reg [7:0] alpha_values [0:3*D-1];
    reg [7:0] beta_values [0:2];
    reg [31:0] expected_values [0:3*D-1];
    reg [31:0] read_value;
    integer index;
    integer errors = 0;

    always #5 clk = ~clk;

    kda_axi_top #(.HEAD_DIM(D), .LANES(LANES)) dut (
        .s_axi_aclk(clk), .s_axi_aresetn(rst_n),
        .s_axi_awaddr(awaddr), .s_axi_awprot(awprot), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arprot(arprot), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready)
    );

    task axi_write;
        input [15:0] address;
        input [31:0] data;
        begin
            @(negedge clk);
            awaddr = address;
            wdata = data;
            awvalid = 1'b1;
            wvalid = 1'b1;
            while (!(awready && wready)) @(negedge clk);
            @(negedge clk);
            awvalid = 1'b0;
            wvalid = 1'b0;
            while (!bvalid) @(negedge clk);
            if (bresp != 2'b00) begin
                $display("write response error address=%h response=%b", address, bresp);
                errors = errors + 1;
            end
            @(negedge clk);
        end
    endtask

    task axi_read;
        input [15:0] address;
        output [31:0] data;
        begin
            @(negedge clk);
            araddr = address;
            arvalid = 1'b1;
            while (!arready) @(negedge clk);
            @(negedge clk);
            arvalid = 1'b0;
            while (!rvalid) @(negedge clk);
            data = rdata;
            if (rresp != 2'b00) begin
                $display("read response error address=%h response=%b", address, rresp);
                errors = errors + 1;
            end
            @(negedge clk);
        end
    endtask

    task wait_done;
        begin : wait_loop
            for (index = 0; index < 10000; index = index + 1) begin
                axi_read(16'h0008, read_value);
                if (read_value[1] && !read_value[0])
                    disable wait_loop;
            end
            $fatal(1, "AXI accelerator timeout");
        end
    endtask

    initial begin
        $readmemh("sim/fixtures/q.memh", q_values);
        $readmemh("sim/fixtures/k.memh", k_values);
        $readmemh("sim/fixtures/v.memh", v_values);
        $readmemh("sim/fixtures/alpha.memh", alpha_values);
        $readmemh("sim/fixtures/beta.memh", beta_values);
        $readmemh("sim/fixtures/expected.memh", expected_values);

        repeat (4) @(negedge clk);
        rst_n = 1'b1;

        axi_read(16'h0000, read_value);
        if (read_value !== 32'h4b444131) begin
            $display("ID mismatch actual=%h", read_value);
            errors = errors + 1;
        end
        axi_read(16'h0010, read_value);
        if (read_value !== D) errors = errors + 1;
        axi_read(16'h0014, read_value);
        if (read_value !== LANES) errors = errors + 1;

        axi_write(16'h0004, 32'd2);
        wait_done();
        for (index = 0; index < D; index = index + 1) begin
            axi_write(16'h1000 + index*4, {24'd0, q_values[index]});
            axi_write(16'h1400 + index*4, {24'd0, k_values[index]});
            axi_write(16'h1800 + index*4, {24'd0, v_values[index]});
            axi_write(16'h1c00 + index*4, {24'd0, alpha_values[index]});
        end
        axi_write(16'h0018, {24'd0, beta_values[0]});
        axi_write(16'h0004, 32'd1);
        wait_done();
        axi_read(16'h000c, read_value);
        if (read_value !== EXPECTED_CYCLES) begin
            $display("AXI cycle mismatch actual=%0d expected=%0d", read_value, EXPECTED_CYCLES);
            errors = errors + 1;
        end
        for (index = 0; index < D; index = index + 1) begin
            axi_read(16'h2000 + index*4, read_value);
            if ($signed(read_value) !== $signed(expected_values[index])) begin
                $display("AXI output mismatch index=%0d actual=%0d expected=%0d", index, $signed(read_value), $signed(expected_values[index]));
                errors = errors + 1;
            end
        end

        if (errors == 0) begin
            $display("PASS kda_axi head_dim=%0d lanes=%0d", D, LANES);
            $finish;
        end
        $fatal(1, "FAIL kda_axi errors=%0d", errors);
    end
endmodule
