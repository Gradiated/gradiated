// Monitor the three structurally serial RMSNorm instances separately.
integer norm_products, norm_profile, norm_outputs, norm_scalar_outputs;
integer norm_depth[3], norm_waits[3], norm_steps[3], norm_operations[3][4];
logic [8:0] normalization_phase[3];
logic [3:0] norm_state[3];
logic [4:0] norm_coord[3], norm_return[3], norm_index[3];
logic norm_iteration[3], norm_multiplying[3], norm_launch[3], norm_finish[3];
logic norm_output[3], norm_clip[3], norm_error[3], norm_scalar_output[3], norm_scalar_error[3];
logic [63:0] norm_left[3], norm_right[3];
logic [127:0] norm_magnitude[3];
logic signed [15:0] norm_value[3];
logic signed [63:0] norm_scalar_value[3];
logic signed [7:0] norm_scalar_exponent[3];

`ifdef DSP_NORMALIZATION
`define MONITOR_NORM_MUL(N,PATH) \
    assign norm_right[N]=dut.core.PATH.scalar.multiplier; \
    assign norm_magnitude[N]=dut.core.PATH.scalar.product_sum; \
    assign norm_launch[N]=dut.core.PATH.scalar.state==5'd3; \
    assign norm_finish[N]=dut.core.PATH.scalar.state==5'd21; \
    assign norm_multiplying[N]=norm_launch[N] || (dut.core.PATH.scalar.state>=5'd18 && \
                                               dut.core.PATH.scalar.state<=5'd21);
`else
`define MONITOR_NORM_MUL(N,PATH) \
    assign norm_right[N]=dut.core.PATH.scalar.product_sum[63:0]; \
    assign norm_magnitude[N]=dut.core.PATH.scalar.next_product; \
    assign norm_multiplying[N]=dut.core.PATH.scalar.state==5'd3; \
    assign norm_launch[N]=norm_multiplying[N] && dut.core.PATH.scalar.remaining==7'd16; \
    assign norm_finish[N]=norm_multiplying[N] && dut.core.PATH.scalar.remaining==7'd1;
`endif

`define MONITOR_NORM(N,PATH,PHASE) \
    assign normalization_phase[N]=9'(PHASE); \
    assign norm_state[N]=dut.core.PATH.state; \
    assign norm_coord[N]=dut.core.PATH.coordinate; \
    assign norm_return[N]=dut.core.PATH.scalar.return_state; \
    assign norm_iteration[N]=dut.core.PATH.scalar.iteration; \
    assign norm_left[N]=dut.core.PATH.scalar.multiplicand; \
    assign norm_output[N]=dut.core.PATH.result_valid && dut.core.PATH.result_ready; \
    assign norm_index[N]=dut.core.PATH.result_index; \
    assign norm_value[N]=dut.core.PATH.result; \
    assign norm_clip[N]=dut.core.PATH.saturated; \
    assign norm_error[N]=dut.core.PATH.error; \
    assign norm_scalar_output[N]=dut.core.PATH.scalar_result_valid && dut.core.PATH.scalar_result_ready; \
    assign norm_scalar_value[N]=dut.core.PATH.scalar_result; \
    assign norm_scalar_exponent[N]=dut.core.PATH.scalar_exponent; \
    assign norm_scalar_error[N]=dut.core.PATH.scalar_error; \
    `MONITOR_NORM_MUL(N,PATH)

`MONITOR_NORM(0,norm1,4)
`MONITOR_NORM(1,norm2,12)
`MONITOR_NORM(2,normfinal,16)
`undef MONITOR_NORM
`undef MONITOR_NORM_MUL

initial begin
    norm_products=$fopen("norm-products.txt","w");
    norm_profile=$fopen("norm-profile.txt","w");
    norm_outputs=$fopen("norm-results.txt","w");
    norm_scalar_outputs=$fopen("norm-scalar-results.txt","w");
    if (norm_products==0 || norm_profile==0 || norm_outputs==0 || norm_scalar_outputs==0)
        $fatal(1,"Cannot open normalization replay traces");
end

always @(posedge aclk) if (aresetn && observing) begin
    if (int'(norm_multiplying[0])+int'(norm_multiplying[1])+int'(norm_multiplying[2])>1)
        $fatal(1,"Normalization products overlapped");
    for (int lane=0; lane<3; lane++) begin
        if (int'(dut.core_phase)==int'(normalization_phase[lane])) begin
            int origin;
            norm_waits[lane]++;
            if (norm_multiplying[lane]) begin
                case(norm_state[lane])
                    4'd2: origin=0; // SQUARE_WAIT
                    4'd6: origin=1; // RSQRT_WAIT
                    4'd8: origin=2; // XY_WAIT
                    4'd10: origin=3; // GAIN_WAIT
                    default: $fatal(1,"Unexpected normalization product origin");
                endcase
                norm_steps[lane]++;
                if (norm_launch[lane])
                    $fwrite(norm_products,"A %0d %0d %0d %0d %0d %0d %h %h\n",lane,norm_depth[lane]+1,origin,
                            norm_coord[lane],norm_return[lane],norm_iteration[lane],norm_left[lane],norm_right[lane]);
                if (norm_finish[lane]) begin
                    norm_operations[lane][origin]++;
                    $fwrite(norm_products,"P %0d %0d %0d %0d %0d %0d %h\n",lane,norm_depth[lane]+1,origin,
                            norm_coord[lane],norm_return[lane],norm_iteration[lane],norm_magnitude[lane]);
                end
            end
            if (norm_scalar_output[lane])
                $fwrite(norm_scalar_outputs,"%0d %0d %0d %0d %0d %0d %0d\n",lane,norm_depth[lane]+1,
                        norm_state[lane],norm_coord[lane],norm_scalar_value[lane],norm_scalar_exponent[lane],
                        norm_scalar_error[lane]);
            if (norm_output[lane]) begin
                $fwrite(norm_outputs,"%0d %0d %0d %0d %0d %0d\n",lane,norm_depth[lane]+1,
                        norm_index[lane],norm_value[lane],norm_clip[lane],norm_error[lane]);
                if (norm_index[lane]==5'd31) begin
                    norm_depth[lane]++;
                    $fwrite(norm_profile,"%0d %0d %0d %0d %0d %0d %0d %0d\n",lane,norm_depth[lane],
                            norm_waits[lane],norm_steps[lane],norm_operations[lane][0],norm_operations[lane][1],
                            norm_operations[lane][2],norm_operations[lane][3]);
                    norm_waits[lane]=0;
                    norm_steps[lane]=0;
                    for(int index=0; index<4; index++) norm_operations[lane][index]=0;
                end
            end
        end else if (norm_multiplying[lane] || norm_output[lane]) $fatal(1,"Normalization work escaped its phase");
    end
end

final begin
    for(int lane=0; lane<3; lane++)
        if (norm_waits[lane] || norm_steps[lane]) $fatal(1,"Incomplete normalization capture");
    $fclose(norm_products);
    $fclose(norm_profile);
    $fclose(norm_outputs);
    $fclose(norm_scalar_outputs);
end
