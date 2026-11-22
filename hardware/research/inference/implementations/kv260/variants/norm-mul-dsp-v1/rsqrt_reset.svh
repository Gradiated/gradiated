        // Reset at each multiplier state for each of the six nested products.
        // Every recovery reloads the table and executes the complete RSQRT.
        for(int product_index=0; product_index<6; product_index++) begin
            for(int stage=0; stage<5; stage++) begin
                load_table({folder,"/rsqrt.hex"},1);
                op=4; a=64'sd4294967296; b=0; shift=0; cmd_valid=1;
                @(negedge clk);cmd_valid=0;
                for(int wait_clock=0; wait_clock<400; wait_clock++) begin
                    if(state[1]==MUL_STEP &&
                       candidate.return_state==5'(14+product_index%3) &&
                       int'(candidate.iteration)==product_index/3) break;
                    if(wait_clock==399 || result_valid[1]) $fatal(1,"Missed reciprocal-sqrt reset target");
                    @(negedge clk);
                end
                repeat(stage) @(negedge clk);
                if(state[1]!=(stage==0 ? MUL_STEP : 5'(int'(MUL_ROWS)+stage-1)))
                    $fatal(1,"Reset missed reciprocal-sqrt multiplier state");
                reset=1;
                @(negedge clk);reset=0;
                #1;
                if(cmd_ready!=2'b11 || result_valid!=0 || error!=0)
                    $fatal(1,"Reciprocal-sqrt reset left a stale result");
                load_table({folder,"/rsqrt.hex"},1);
                check_case(count+5+5*product_index+stage,64'sd1073741824,8'sd0,0,0,6);

                // The next probe must start after another clean table reset.
                reset=1;
                @(negedge clk);reset=0;
                #1;
            end
        end
        $display("PASS thirty reciprocal-sqrt cancellations and fresh-table restarts");
