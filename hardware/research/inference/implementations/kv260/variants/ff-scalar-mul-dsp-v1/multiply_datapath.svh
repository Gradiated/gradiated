    // These registers carry only in-flight data. The state selects each new
    // write before its value is consumed, including after synchronous reset.
    for (genvar row=0; row<4; row++) begin : mul_row
        logic [31:0] partial[0:3];
        for (genvar col=0; col<4; col++) begin : mul_limb
            logic signed [16:0] a_limb, b_limb;
            (* use_dsp = "yes" *) logic signed [33:0] limb_product;
            assign a_limb=$signed({1'b0,multiplicand[16*col+:16]});
            assign b_limb=$signed({1'b0,multiplier[16*row+:16]});
            always_ff @(posedge clk)
                if(!reset && state==MUL_STEP) limb_product<=a_limb*b_limb;
            assign partial[col]=limb_product[31:0];
        end

        // The even partials are separated by 32 bits and already disjoint.
        // The odd partials are disjoint too, shifted another 16 bits.
        (* use_dsp = "no" *) logic [79:0] row_sum;
        assign row_sum={16'd0,partial[2],partial[0]}+{partial[3],partial[1],16'd0};
        always_ff @(posedge clk)
            if(!reset && state==MUL_ROWS) product_rows[row]<=row_sum;
    end

    for (genvar half=0; half<2; half++) begin : mul_half
        (* use_dsp = "no" *) logic [95:0] half_sum;
        assign half_sum={16'd0,product_rows[2*half]}+{product_rows[2*half+1],16'd0};
        always_ff @(posedge clk)
            if(!reset && state==MUL_PAIRS) product_halves[half]<=half_sum;
    end

    (* use_dsp = "no" *) logic [127:0] full_sum;
    assign full_sum={32'd0,product_halves[0]}+{product_halves[1],32'd0};
    always_ff @(posedge clk)
        if(!reset && state==MUL_REDUCE) product_sum<=full_sum;

