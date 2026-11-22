// Capture each feed-forward product before sign handling and every wait at each depth.
integer multiply_trace, ff_profile, ff_elements;
integer observed_ff_ticks, pair_stalls, products[3], multiplier_ticks[3];
logic [63:0] left_magnitude, right_magnitude;
bit multiply_start_seen, multiply_finish_seen, multiply_busy;
logic [127:0] magnitude_product;

initial begin
    multiply_trace=$fopen("feedforward-products.txt","w");
    ff_profile=$fopen("feedforward-profile.txt","w");
    ff_elements=$fopen("feedforward-elements.txt","w");
    if (!multiply_trace || !ff_profile || !ff_elements)
        $fatal(1,"Cannot open feed-forward replay traces");
end

always_comb begin
    left_magnitude=dut.core.ff.scalar.multiplicand;
`ifdef PARTIAL_MULTIPLIER
    right_magnitude=dut.core.ff.scalar.multiplier;
    magnitude_product=dut.core.ff.scalar.product_sum;
    multiply_start_seen=dut.core.ff.scalar.state==dut.core.ff.scalar.MUL_STEP;
    multiply_finish_seen=dut.core.ff.scalar.state==dut.core.ff.scalar.MUL_FINISH;
    multiply_busy=multiply_start_seen || dut.core.ff.scalar.state==dut.core.ff.scalar.MUL_ROWS ||
                  dut.core.ff.scalar.state==dut.core.ff.scalar.MUL_PAIRS ||
                  dut.core.ff.scalar.state==dut.core.ff.scalar.MUL_REDUCE || multiply_finish_seen;
`else
    right_magnitude=dut.core.ff.scalar.product_sum[63:0];
    magnitude_product=dut.core.ff.scalar.next_product;
    multiply_busy=dut.core.ff.scalar.state==dut.core.ff.scalar.MUL_STEP;
    multiply_start_seen=multiply_busy && dut.core.ff.scalar.remaining==7'd16;
    multiply_finish_seen=multiply_busy && dut.core.ff.scalar.remaining==7'd1;
`endif
end

always @(posedge aclk) if (aresetn && observing && int'(dut.core_phase)==14) begin
    int origin;
    observed_ff_ticks++;
    if (dut.core.ff.state==dut.core.ff.PAIR && !(dut.core.ff.g_valid && dut.core.ff.u_valid)) pair_stalls++;
    if (multiply_busy) begin
        case (dut.core.ff.state)
            dut.core.ff.EXP_WAIT: origin=0;
            dut.core.ff.GATE_MUL_WAIT: origin=1;
            dut.core.ff.HIDDEN_MUL_WAIT: origin=2;
            default: $fatal(1,"Unexpected feed-forward product origin");
        endcase
        multiplier_ticks[origin]++;
        if (multiply_start_seen) begin
            $fwrite(multiply_trace,"A %0d %0d %0d %h %h\n",dut.core_context_count,dut.core.ff.index,
                    origin,left_magnitude,right_magnitude);
        end
        if (multiply_finish_seen) begin
            products[origin]++;
            $fwrite(multiply_trace,"P %0d %0d %0d %h\n",dut.core_context_count,dut.core.ff.index,
                    origin,magnitude_product);
        end
    end
    if (dut.core.ff.element_valid)
        $fwrite(ff_elements,"%0d %0d %0d %0d %0d %0d %0d\n",dut.core_context_count,
                dut.core.ff.element_index,dut.core.ff.element_gate,dut.core.ff.element_up,
                dut.core.ff.element_silu,dut.core.ff.element_hidden,dut.core.ff.element_saturated);
    if (dut.core.ff.result_valid && dut.core.ff.result_ready && dut.core.ff.result_row==9'd31) begin
        $fwrite(ff_profile,"%0d %0d %0d %0d %0d %0d %0d %0d %0d\n",dut.core_context_count,observed_ff_ticks,pair_stalls,
                products[0],products[1],products[2],multiplier_ticks[0],multiplier_ticks[1],multiplier_ticks[2]);
        observed_ff_ticks=0;
        pair_stalls=0;
        foreach(products[i]) begin products[i]=0; multiplier_ticks[i]=0; end
    end
end

final begin
    if (observed_ff_ticks || pair_stalls) $fatal(1,"Incomplete feed-forward capture");
    $fclose(multiply_trace);
    $fclose(ff_profile);
    $fclose(ff_elements);
end
